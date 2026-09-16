package core

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/dagger/dagger/engine/filesync"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	bkclient "github.com/dagger/dagger/internal/buildkit/client"
	"github.com/dagger/dagger/internal/buildkit/identity"
	digest "github.com/opencontainers/go-digest"
	"github.com/vektah/gqlparser/v2/ast"
	"google.golang.org/grpc"

	"github.com/dagger/dagger/dagql"
)

type ClientFilesyncMirror struct {
	StableClientID string
	Drive          string
	EphemeralID    string

	mu sync.Mutex

	snapshot      bkcache.MutableRef
	layoutVersion int

	mounter bkcache.Mounter
	mntPath string

	sharedState *filesync.MirrorSharedState
	usageCount  int
}

var _ dagql.PersistedObject = (*ClientFilesyncMirror)(nil)
var _ dagql.PersistedObjectDecoder = (*ClientFilesyncMirror)(nil)
var _ dagql.OnReleaser = (*ClientFilesyncMirror)(nil)

func (*ClientFilesyncMirror) Type() *ast.Type {
	return &ast.Type{
		NamedType: "ClientFilesyncMirror",
		NonNull:   true,
	}
}

func (*ClientFilesyncMirror) TypeDescription() string {
	return "An internal persistent filesync mirror."
}

func (m *ClientFilesyncMirror) PersistedSnapshotRefLinks() []dagql.PersistedSnapshotRefLink {
	if m == nil {
		return nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.snapshot == nil {
		return nil
	}
	return []dagql.PersistedSnapshotRefLink{{
		RefKey: m.snapshot.SnapshotID(),
		Role:   "snapshot",
	}}
}

func (m *ClientFilesyncMirror) CacheUsageMayChange() bool {
	return true
}

func (m *ClientFilesyncMirror) CacheUsageIdentities() []string {
	if m == nil {
		return nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.snapshot == nil {
		return nil
	}
	return []string{m.snapshot.SnapshotID()}
}

func (m *ClientFilesyncMirror) CacheUsageSize(ctx context.Context, _ dagql.CacheUsageSizeProvider, identity string) (int64, bool, error) {
	if m == nil {
		return 0, false, nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	snapshot := m.snapshot
	if snapshot == nil || snapshot.SnapshotID() != identity {
		return 0, false, nil
	}
	// The mirror (including its inode cache) grows and shrinks without changing
	// snapshot identity. Size caches metadata, so CacheUsageMayChange alone is
	// insufficient. Serialize size refreshes and never return that stale value.
	if err := snapshot.InvalidateSize(ctx); err != nil {
		return 0, false, err
	}
	size, err := snapshot.Size(ctx)
	if err != nil {
		return 0, false, err
	}
	return size, true, nil
}

type persistedClientFilesyncMirrorPayload struct {
	StableClientID string `json:"stableClientID"`
	Drive          string `json:"drive,omitempty"`
	LayoutVersion  int    `json:"layoutVersion,omitempty"`
}

func (m *ClientFilesyncMirror) EncodePersistedObject(ctx context.Context, cache dagql.PersistedObjectCache) (dagql.PersistedObjectEncoding, error) {
	_ = ctx
	_ = cache
	if m == nil {
		return dagql.PersistedObjectEncoding{}, fmt.Errorf("encode persisted client filesync mirror: nil mirror")
	}
	if m.StableClientID == "" {
		return dagql.PersistedObjectEncoding{}, fmt.Errorf("encode persisted client filesync mirror: stable client id is empty")
	}
	m.mu.Lock()
	var links []dagql.PersistedSnapshotRefLink
	if m.snapshot != nil {
		links = []dagql.PersistedSnapshotRefLink{{
			RefKey: m.snapshot.SnapshotID(),
			Role:   "snapshot",
		}}
	}
	layoutVersion := m.layoutVersion
	m.mu.Unlock()
	payload, err := json.Marshal(persistedClientFilesyncMirrorPayload{
		StableClientID: m.StableClientID,
		Drive:          m.Drive,
		LayoutVersion:  layoutVersion,
	})
	if err != nil {
		return dagql.PersistedObjectEncoding{}, err
	}
	return dagql.PersistedObjectEncoding{
		JSON:          payload,
		SnapshotLinks: links,
	}, nil
}

func (*ClientFilesyncMirror) DecodePersistedObject(ctx context.Context, dag *dagql.Server, resultID uint64, _ *dagql.ResultCall, payload json.RawMessage) (dagql.Typed, error) {
	var persisted persistedClientFilesyncMirrorPayload
	if err := json.Unmarshal(payload, &persisted); err != nil {
		return nil, fmt.Errorf("decode persisted client filesync mirror payload: %w", err)
	}
	mirror := &ClientFilesyncMirror{
		StableClientID: persisted.StableClientID,
		Drive:          persisted.Drive,
		layoutVersion:  persisted.LayoutVersion,
	}
	if mirror.layoutVersion < 0 || mirror.layoutVersion > 1 {
		return nil, fmt.Errorf("unsupported filesync mirror layout %d", mirror.layoutVersion)
	}
	if resultID == 0 {
		return mirror, nil
	}

	link, err := loadPersistedSnapshotLinkByResultID(ctx, dag, resultID, "client filesync mirror", "snapshot")
	if err != nil {
		return nil, err
	}
	query, err := persistedDecodeQuery(dag)
	if err != nil {
		return nil, err
	}
	ref, err := query.SnapshotManager().GetMutableBySnapshotID(ctx, link.RefKey, bkcache.NoUpdateLastUsed)
	if err != nil {
		return nil, fmt.Errorf("reopen persisted client filesync mirror snapshot %q: %w", link.RefKey, err)
	}
	mirror.snapshot = ref
	return mirror, nil
}

func (m *ClientFilesyncMirror) OnRelease(ctx context.Context) error {
	if m == nil {
		return nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.usageCount = 0
	rerr := m.releaseRuntimeLocked()
	if m.snapshot != nil {
		rerr = errorsJoin(rerr, m.snapshot.Release(ctx))
		m.snapshot = nil
	}
	return rerr
}

func (m *ClientFilesyncMirror) EnsureCreated(ctx context.Context, query *Query) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.snapshot != nil {
		return nil
	}
	ref, err := query.SnapshotManager().New(
		ctx,
		nil,
		nil,
		bkcache.WithRecordType(bkclient.UsageRecordTypeLocalSource),
		bkcache.WithDescription(func() string {
			if m.StableClientID != "" {
				return fmt.Sprintf("client filesync mirror for %s%s", m.Drive, m.StableClientID)
			}
			return fmt.Sprintf("ephemeral client filesync mirror for %s%s", m.Drive, m.EphemeralID)
		}()),
	)
	if err != nil {
		return err
	}
	m.snapshot = ref
	m.layoutVersion = 1
	return nil
}

func (m *ClientFilesyncMirror) Snapshot(
	ctx context.Context,
	query *Query,
	callerConn *grpc.ClientConn,
	clientPath string,
	opts filesync.SnapshotOpts,
) (bkcache.ImmutableRef, digest.Digest, error) {
	sharedState, release, err := m.acquire(ctx, query)
	if err != nil {
		return nil, "", err
	}
	defer func() {
		_ = release(context.WithoutCancel(ctx))
	}()
	return filesync.NewFileSyncer(filesync.FileSyncerOpt{
		CacheAccessor: query.SnapshotManager(),
	}).Snapshot(ctx, sharedState, callerConn, clientPath, opts)
}

func (m *ClientFilesyncMirror) acquire(ctx context.Context, query *Query) (_ *filesync.MirrorSharedState, release func(context.Context) error, err error) {
	m.mu.Lock()
	if err := m.ensureRuntimeLocked(ctx, query); err != nil {
		m.mu.Unlock()
		return nil, nil, err
	}
	m.usageCount++
	sharedState := m.sharedState
	m.mu.Unlock()
	return sharedState, func(_ context.Context) error {
		m.mu.Lock()
		defer m.mu.Unlock()
		m.usageCount--
		if m.usageCount > 0 {
			return nil
		}
		return m.releaseRuntimeLocked()
	}, nil
}

func (m *ClientFilesyncMirror) ensureRuntimeLocked(ctx context.Context, query *Query) error {
	if m.sharedState != nil {
		return nil
	}
	if m.snapshot == nil {
		ref, err := query.SnapshotManager().New(
			ctx,
			nil,
			nil,
			bkcache.WithRecordType(bkclient.UsageRecordTypeLocalSource),
			bkcache.WithDescription(func() string {
				if m.StableClientID != "" {
					return fmt.Sprintf("client filesync mirror for %s%s", m.Drive, m.StableClientID)
				}
				return fmt.Sprintf("ephemeral client filesync mirror for %s%s", m.Drive, m.EphemeralID)
			}()),
		)
		if err != nil {
			return err
		}
		m.snapshot = ref
		m.layoutVersion = 1
	}

	mountable, err := m.snapshot.Mount(ctx, false)
	if err != nil {
		return err
	}
	m.mounter = bkcache.LocalMounter(mountable)
	m.mntPath, err = m.mounter.Mount()
	if err != nil {
		return err
	}
	if m.layoutVersion == 1 {
		filesPath := filepath.Join(m.mntPath, "files")
		blobsPath := filepath.Join(m.mntPath, "blobs")
		if err := os.MkdirAll(filesPath, 0o755); err != nil {
			return err
		}
		if err := os.MkdirAll(blobsPath, 0o700); err != nil {
			return err
		}
		m.sharedState = filesync.NewMirrorSharedStateWithFileCache(filesPath, blobsPath)
	} else {
		// Existing persisted mirrors keep their original layout and copy path.
		m.sharedState = filesync.NewMirrorSharedState(m.mntPath)
	}
	return nil
}

func (m *ClientFilesyncMirror) releaseRuntimeLocked() (rerr error) {
	if m.mounter != nil {
		rerr = errorsJoin(rerr, m.mounter.Unmount())
		m.mounter = nil
	}
	m.mntPath = ""
	m.sharedState = nil
	return rerr
}

func errorsJoin(errs ...error) error {
	var out error
	for _, err := range errs {
		if err == nil {
			continue
		}
		if out == nil {
			out = err
		} else {
			out = fmt.Errorf("%w; %w", out, err)
		}
	}
	return out
}

func NewEphemeralClientFilesyncMirror(drive string) *ClientFilesyncMirror {
	return &ClientFilesyncMirror{
		Drive:       drive,
		EphemeralID: identity.NewID(),
	}
}
