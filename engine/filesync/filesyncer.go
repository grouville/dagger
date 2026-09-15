package filesync

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	remotefilesync "github.com/dagger/dagger/internal/buildkit/session/filesync"
	"github.com/dagger/dagger/internal/buildkit/util/bklog"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/opencontainers/go-digest"
	"google.golang.org/grpc"

	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/client/pathutil"
	"github.com/dagger/dagger/util/hashutil"
	telemetry "github.com/dagger/otel-go"
)

type FileSyncer struct {
	cacheManager bkcache.Accessor
}

type FileSyncerOpt struct {
	CacheAccessor bkcache.Accessor
}

func NewFileSyncer(opt FileSyncerOpt) *FileSyncer {
	return &FileSyncer{cacheManager: opt.CacheAccessor}
}

type SnapshotOpts struct {
	IncludePatterns []string
	ExcludePatterns []string
	FollowPaths     []string
	GitIgnore       bool
	CacheBuster     string
	RelativePath    string
}

func (ls *FileSyncer) Snapshot(
	ctx context.Context,
	sharedState *MirrorSharedState,
	callerConn *grpc.ClientConn,
	clientPath string,
	opts SnapshotOpts,
) (bkcache.ImmutableRef, digest.Digest, error) {
	if sharedState == nil {
		return nil, "", fmt.Errorf("filesync mirror shared state is nil")
	}
	if callerConn == nil {
		return nil, "", fmt.Errorf("filesync caller conn is nil")
	}
	if opts.RelativePath == "." {
		opts.RelativePath = ""
	}
	ref, dgst, err := ls.snapshot(ctx, sharedState, callerConn, clientPath, opts)
	if err != nil {
		return nil, "", fmt.Errorf("failed to snapshot: %w", err)
	}
	return ref, dgst, nil
}

func (ls *FileSyncer) snapshot(
	ctx context.Context,
	sharedState *MirrorSharedState,
	callerConn *grpc.ClientConn,
	clientPath string,
	opts SnapshotOpts,
) (_ bkcache.ImmutableRef, _ digest.Digest, rerr error) {
	// Encapsulated like the resolver's "pulling" span: hidden unless it
	// fails, surfacing as a labeled progress row only when bytes actually
	// move (an unchanged directory syncs nothing).
	ctx, span := Tracer(ctx).Start(ctx, "uploading "+clientPath,
		telemetry.Encapsulated(), telemetry.Encapsulate())
	defer telemetry.EndWithCause(span, &rerr)

	statCtx := engine.LocalImportOpts{
		Path:              clientPath,
		StatPathOnly:      true,
		StatReturnAbsPath: true,
		StatResolvePath:   true,
	}.AppendToOutgoingContext(ctx)
	diffCopyClient, err := remotefilesync.NewFileSyncClient(callerConn).DiffCopy(statCtx)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create diff copy client: %w", err)
	}

	var statMsg fstypes.Stat
	if err := diffCopyClient.RecvMsg(&statMsg); err != nil {
		diffCopyClient.CloseSend()
		return nil, "", fmt.Errorf("failed to receive stat message: %w", err)
	}
	diffCopyClient.CloseSend()

	clientPath = filepath.Clean(statMsg.Path)
	drive := pathutil.GetDrive(clientPath)
	if drive != "" {
		clientPath = clientPath[len(drive):]
	}

	finalRef, dgst, err := ls.sync(ctx, sharedState, callerConn, drive, clientPath, opts)
	if err != nil {
		return nil, "", fmt.Errorf("failed to sync: %w", err)
	}
	return finalRef, dgst, nil
}

func (ls *FileSyncer) sync(
	ctx context.Context,
	sharedState *MirrorSharedState,
	callerConn *grpc.ClientConn,
	drive string,
	clientPath string,
	opts SnapshotOpts,
) (_ bkcache.ImmutableRef, _ digest.Digest, rerr error) {
	if err := ls.syncParentDirs(ctx, sharedState, callerConn, clientPath, drive, opts); err != nil {
		return nil, "", fmt.Errorf("failed to sync parent dirs: %w", err)
	}

	ctx, cancel := context.WithCancelCause(ctx)
	defer func() {
		cancel(rerr)
	}()

	local, err := newLocalFS(sharedState, clientPath, opts.IncludePatterns, opts.ExcludePatterns, opts.FollowPaths, opts.RelativePath)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create local fs: %w", err)
	}

	// Announce the walk digest of the last sync of this tree. A client whose
	// walk hashes the same sends no stats, and the snapshot it produced last
	// time is reused without touching the mirror. If that snapshot is gone,
	// fall back to a plain sync on a fresh stream.
	walkKey := hashutil.HashStrings(
		"filesync-walk", drive+clientPath, opts.RelativePath, fmt.Sprintf("%t", opts.GitIgnore),
		fmt.Sprint(opts.IncludePatterns), fmt.Sprint(opts.ExcludePatterns), fmt.Sprint(opts.FollowPaths),
	).String()
	remote := newRemoteFS(callerConn, drive+clientPath, opts.IncludePatterns, opts.ExcludePatterns, opts.FollowPaths, opts.GitIgnore)
	if rec, ok := sharedState.walkDigests.get(walkKey); ok {
		remote.knownWalkDigest = rec.walkDigest
		// The stream lives until this function's cancel fires, on every path.
		unchanged, err := remote.begin(ctx)
		if err != nil {
			return nil, "", err
		}
		if unchanged {
			ref, found, err := refForContentDigest(ctx, ls.cacheManager, rec.contentDigest)
			if err != nil {
				return nil, "", err
			}
			if found {
				return ref, rec.contentDigest, nil
			}
			remote = newRemoteFS(callerConn, drive+clientPath, opts.IncludePatterns, opts.ExcludePatterns, opts.FollowPaths, opts.GitIgnore)
		}
	}

	ref, dgst, err := local.Sync(ctx, remote, ls.cacheManager, false)
	if err != nil {
		return nil, "", err
	}
	if remote.walkDigest != "" {
		sharedState.walkDigests.set(walkKey, walkDigestRecord{walkDigest: remote.walkDigest, contentDigest: dgst})
	}
	return ref, dgst, nil
}

func (ls *FileSyncer) syncParentDirs(
	ctx context.Context,
	sharedState *MirrorSharedState,
	callerConn *grpc.ClientConn,
	clientPath string,
	drive string,
	opts SnapshotOpts,
) (rerr error) {
	ctx, cancel := context.WithCancelCause(ctx)
	defer func() {
		cancel(rerr)
	}()

	ctx = bklog.WithLogger(ctx, bklog.G(ctx).WithField("parentSync", "y"))

	include := strings.TrimPrefix(strings.TrimSuffix(clientPath, "/"), "/")
	includes := []string{include}
	excludes := []string{include + "/*"}
	root := "/"
	if drive != "" {
		root = drive + "/"
	}

	remote := newRemoteFS(callerConn, root, includes, excludes, nil, false)
	local, err := newLocalFS(sharedState, "/", includes, excludes, nil, opts.RelativePath)
	if err != nil {
		return fmt.Errorf("failed to create local fs: %w", err)
	}
	_, _, err = local.Sync(ctx, remote, ls.cacheManager, true)
	if err != nil {
		return fmt.Errorf("failed to sync to local fs: %w", err)
	}
	return nil
}
