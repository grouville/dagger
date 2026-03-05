package filesync

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	cfs "github.com/containerd/continuity/fs"
	"github.com/containerd/continuity/sysx"
	bkcache "github.com/dagger/dagger/internal/buildkit/cache"
	bkcontenthash "github.com/dagger/dagger/internal/buildkit/cache/contenthash"
	"github.com/dagger/dagger/internal/buildkit/session"
	"github.com/dagger/dagger/internal/buildkit/snapshot"
	"github.com/dagger/dagger/internal/buildkit/util/bklog"
	"github.com/dagger/dagger/internal/fsutil"
	fscopy "github.com/dagger/dagger/internal/fsutil/copy"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/hashutil"
	digest "github.com/opencontainers/go-digest"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
	"golang.org/x/sync/errgroup"
	"golang.org/x/sys/unix"

	"github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/filesync/cas"
	telemetry "github.com/dagger/otel-go"
)

const (
	hashXattrKey                   = "user.daggerContentHash"
	maxParentMaterializeChainDepth = uint32(128)
)

// localFSSharedState is the state shared between all syncs for a given client
type localFSSharedState struct {
	// rootPath is the abs path to the mounted cache ref that we sync all files/dirs for
	// a given client
	rootPath string

	// changeCache is the cache we use to dedupe/cache changes made to the local fs across
	// different syncs (see docs on localFS.Sync for more info)
	changeCache *changeCache
}

type ChangeWithStat struct {
	kind ChangeKind
	stat *HashedStatInfo
}

type CachedChange = *cachedChange

// localFS holds the state for a single sync of a client's fs into our cache
type localFS struct {
	*localFSSharedState

	// the subdir under rootPath that we are syncing, e.g. if the client is syncing in their
	// /foo/bar/ dir this will be /foo/bar and we will be syncing into <rootPath>/foo/bar
	subdir string

	// The actual copy path to use for that sync.
	// In 90% of the case, this will be `/` but if the client is syncing into a parent dir
	// for example to fetch .gitignore patterns then this will be the actual directory to copy.
	copyPath string

	// filterFS is the fs that applies the include/exclude patterns to our view of the current
	// cache filesystem at <rootPath>/<subdir>
	filterFS fsutil.FS
	includes []string // the include patterns we're using for this sync
	excludes []string // the exclude patterns we're using for this sync
	scopeKey cas.ScopeKey
}

func newLocalFS(sharedState *localFSSharedState, subdir string, includes, excludes []string, copyPath string, scopeKey cas.ScopeKey) (*localFS, error) {
	baseFS, err := fsutil.NewFS(filepath.Join(sharedState.rootPath, subdir))
	if err != nil {
		return nil, fmt.Errorf("failed to create base fs: %w", err)
	}

	filterFS, err := fsutil.NewFilterFS(baseFS, &fsutil.FilterOpt{
		IncludePatterns: includes,
		ExcludePatterns: excludes,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create filter fs: %w", err)
	}

	return &localFS{
		localFSSharedState: sharedState,
		subdir:             subdir,
		filterFS:           filterFS,
		includes:           includes,
		excludes:           excludes,
		copyPath:           copyPath,
		scopeKey:           scopeKey,
	}, nil
}

// Sync the given remote fs into the local fs, returning an immutable cache ref containing the files+dirs
// as they appear in the client at the synced in path.
//
// If forParents is true, only the parent directories are synced and no cache ref is returned.
//
// To handle concurrent syncs, this relies on the local.changeCache singleflight group:
//   - Equivalent operations on the same path running in parallel will be deduped
//   - The caching of results of mutations saves repeating work and allows us to identify when the client
//     filesystem is changing in the middle of a sync in such a way that we'd potentially create inconsistent
//     syncs. If we call a mutation op and get a cached result that doesn't match what we applied, we know
//     there was a conflicting change and can error out.
//   - The fact that cache results are held only for the duration of the sync and .Released at the end allows
//     operations on paths to only be cached as long as needed. That way, if the client filesystem changes after
//     a sync in done (which is safe) we won't use cached results and hit an unnecessary conflict error.
//
// NOTE: This currently does not handle resetting parent dir modtimes to match the client. This matches
// upstream for now and avoids extra performance overhead + complication until a need for those modtimes
// matching the client's is proven.
func (local *localFS) Sync( //nolint:gocyclo
	ctx context.Context,
	remote ReadFS,
	cacheManager bkcache.Accessor,
	session session.Group,
	forParents bool,
) (_ bkcache.ImmutableRef, rerr error) {
	var newCopyRef bkcache.MutableRef       // the mutable ref we will copy into with the frozen files+dirs if needed
	var cacheCtx bkcontenthash.CacheContext // track file+dir hashes
	var scopeHead cas.ScopeHead
	var scopeHeadFound bool
	var scopeParentRef bkcache.ImmutableRef
	parentBasedMaterialize := false
	scopeHeadDepthCapped := false

	// skip creating a cache ref if we're only syncing parent dirs
	if !forParents {
		var err error
		if local.scopeKey != "" {
			scopeHeadStore := cas.ScopeHeadStore{Store: cacheManager}
			loadedScopeHead, found, loadErr := scopeHeadStore.Load(ctx, local.scopeKey)
			if loadErr != nil {
				bklog.G(ctx).Warnf("failed to load filesync scope head for %q: %v", local.scopeKey, loadErr)
			} else if found {
				scopeHead = loadedScopeHead
				scopeHeadFound = true
				if !shouldUseParentFromScopeHead(loadedScopeHead) {
					scopeHeadDepthCapped = true
				} else {
					parentRef, getErr := cacheManager.Get(ctx, loadedScopeHead.MaterialRefID, nil)
					if getErr != nil {
						bklog.G(ctx).Warnf(
							"failed to get filesync scope parent ref for %q (ref=%q): %v",
							local.scopeKey,
							loadedScopeHead.MaterialRefID,
							getErr,
						)
					} else {
						scopeParentRef = parentRef
						parentBasedMaterialize = true
					}
				}
			}
		}

		newCopyRef, err = cacheManager.New(ctx, scopeParentRef, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to create new copy ref: %w", err)
		}
		defer func() {
			ctx := context.WithoutCancel(ctx)
			if newCopyRef != nil {
				if err := newCopyRef.Release(ctx); err != nil {
					rerr = errors.Join(rerr, fmt.Errorf("failed to release copy ref: %w", err))
				}
			}
		}()
		defer func() {
			ctx := context.WithoutCancel(ctx)
			if scopeParentRef != nil {
				if err := scopeParentRef.Release(ctx); err != nil {
					rerr = errors.Join(rerr, fmt.Errorf("failed to release scope parent ref: %w", err))
				}
			}
		}()

		cacheCtx, err = bkcontenthash.GetCacheContext(ctx, newCopyRef)
		if err != nil {
			return nil, fmt.Errorf("failed to get cache context: %w", err)
		}
	}

	diffCtx, diffSpan := Tracer(ctx).Start(ctx, "filesync.diff_apply")
	eg, egCtx := errgroup.WithContext(diffCtx)
	diffApplyStart := time.Now()

	// When a file or dir is added, modified, or deleted, we need to apply the change to the local fs. The local.changeCache
	// keeps track of which modifications we have made during this sync on a per-path basis. This is shared between
	// all syncs to the local fs cache ref. That allows us to both de-dupe equivalent changes and to know when
	// conflicting changes are being applied (due to the client filesystem changing during this sync), which would
	// otherwise create inconsistent synced filesystems.
	//
	// We need to release all the cache results from local.changeCache once we are done here to indicate that we no longer
	// care about any future changes made to the paths we hit during the sync, allowing any future changes made
	// on the client filesystem to be synced in without a conflict error.
	var cachedResults []CachedChange
	var cachedResultsMu sync.Mutex
	defer func() {
		for _, cachedResult := range cachedResults {
			cachedResult.release()
		}
	}()

	only := map[string]struct{}{}
	upsertSet := map[string]struct{}{}
	deleteSet := map[string]struct{}{}
	noneSet := map[string]struct{}{}
	ignoredDirs := map[string]struct{}{}
	var addCount, modifyCount, deleteCount, noneCount int
	var deferredHardlinkCount, ignoredPathCount int
	isIgnoredPath := func(path string) bool {
		for {
			if _, ok := ignoredDirs[path]; ok {
				return true
			}
			if path == "." || path == string(os.PathSeparator) {
				break
			}
			next := filepath.Dir(path)
			if next == path {
				break
			}
			path = next
		}
		return false
	}

	// We assert if we find a file/dir in the given relative path to correctly return
	// an error if nothing exist in there.
	// See explanations here: https://github.com/dagger/dagger/pull/10995#issuecomment-3347636652
	relPathFound := false

	// Hardlinks are a bit hard; we can't create them until their source file exists but we sync in files asynchronously.
	// To deal with this we keep track of the hardlinks we need to make and apply them all at once after everything else
	// is done.
	type hardlinkChange struct {
		kind      ChangeKind
		path      string
		upperStat *types.Stat
	}
	var hardlinks []*hardlinkChange
	var hardlinkMu sync.Mutex

	// Track spans per top-level directory
	type rootPathSpan struct {
		span         trace.Span
		start        time.Time
		writtenBytes int64
		maxStop      time.Time
		mu           sync.Mutex
	}
	var rootPathSpans sync.Map
	getRootPath := func(path string) *rootPathSpan {
		rootPath := strings.Split(path, string(os.PathSeparator))[0]

		now := time.Now()
		dirSpan := &rootPathSpan{
			start:   now,
			maxStop: now,
			mu:      sync.Mutex{},
		}

		rps, _ := rootPathSpans.LoadOrStore(rootPath, dirSpan)
		rps.(*rootPathSpan).mu.Lock()
		if rps.(*rootPathSpan).span == nil {
			_, span := Tracer(egCtx).Start(egCtx, rootPath)
			rps.(*rootPathSpan).span = span
		}
		rps.(*rootPathSpan).mu.Unlock()

		return rps.(*rootPathSpan)
	}

	defer func() {
		rootPathSpans.Range(func(_, value any) bool {
			dirSpan := value.(*rootPathSpan)
			dirSpan.span.End(trace.WithTimestamp(dirSpan.maxStop))
			return true
		})
	}()

	doubleWalkDiff(egCtx, eg, local, remote, func(kind ChangeKind, path string, lowerStat, upperStat *types.Stat) error {
		if upperStat != nil && upperStat.GitIgnored {
			ignoredPathCount++
			if upperStat.IsDir() {
				ignoredDirs[path] = struct{}{}
			}
			return nil
		}
		switch kind {
		case ChangeKindAdd, ChangeKindModify:
			if kind == ChangeKindAdd {
				addCount++
			} else {
				modifyCount++
			}
			switch {
			case upperStat.IsDir():
				appliedChange, err := local.Mkdir(egCtx, kind, path, upperStat)
				if err != nil {
					return err
				}
				cachedResultsMu.Lock()
				cachedResults = append(cachedResults, appliedChange)
				only[path] = struct{}{}
				upsertSet[path] = struct{}{}
				cachedResultsMu.Unlock()

				doHandle := cacheCtx != nil
				if local.copyPath != "" {
					path, doHandle = strings.CutPrefix(path, local.copyPath)
				}
				if doHandle {
					relPathFound = true
					applied := appliedChange.result()
					if err := cacheCtx.HandleChange(applied.kind, path, applied.stat, nil); err != nil {
						return fmt.Errorf("failed to handle change in content hasher: %w", err)
					}
				}

				return nil

			case upperStat.Mode&uint32(os.ModeDevice) != 0 || upperStat.Mode&uint32(os.ModeNamedPipe) != 0:
				// NOTE: not handling devices for now since they are extremely non-portable and dubious in terms
				// of real utility vs. enabling bizarre hacks
				bklog.G(ctx).Warnf("skipping device file %q", path)
				return nil

			case upperStat.Mode&uint32(os.ModeSymlink) != 0:
				appliedChange, err := local.Symlink(egCtx, kind, path, upperStat)
				if err != nil {
					return err
				}
				cachedResultsMu.Lock()
				cachedResults = append(cachedResults, appliedChange)
				only[path] = struct{}{}
				upsertSet[path] = struct{}{}
				cachedResultsMu.Unlock()

				doHandle := cacheCtx != nil
				if local.copyPath != "" {
					path, doHandle = strings.CutPrefix(path, local.copyPath)
				}
				if doHandle {
					relPathFound = true
					applied := appliedChange.result()
					if err := cacheCtx.HandleChange(applied.kind, path, applied.stat, nil); err != nil {
						return fmt.Errorf("failed to handle change in content hasher: %w", err)
					}
				}

				return nil

			case upperStat.Linkname != "":
				// delay hardlinks until after everything else so we know the source of the link exists
				deferredHardlinkCount++
				hardlinkMu.Lock()
				hardlinks = append(hardlinks, &hardlinkChange{
					kind:      kind,
					path:      path,
					upperStat: upperStat,
				})
				hardlinkMu.Unlock()

				return nil

			default:
				eg.Go(func() error {
					// since we can't really know when a root path is done as
					// all files are synced in parallel, we track everything
					// we see and then change the span end time before returning.
					rootPathSpan := getRootPath(path)

					appliedChange, written, werr := local.WriteFile(ctx, kind, path, upperStat, remote)

					writeEnd := time.Now()
					m := telemetry.Meter(ctx, "dagger.io/filesync")
					fsMetric, err := m.Int64Gauge(telemetry.FilesyncWrittenBytes)
					if err != nil {
						return err
					}
					attrs := []attribute.KeyValue{
						attribute.String(telemetry.MetricsTraceIDAttr, rootPathSpan.span.SpanContext().TraceID().String()),
						attribute.String(telemetry.MetricsSpanIDAttr, rootPathSpan.span.SpanContext().SpanID().String()),
					}
					rootPathSpan.mu.Lock()
					rootPathSpan.writtenBytes += written
					fsMetric.Record(ctx, written, metric.WithAttributes(attrs...))
					// only track the max(end) of all the files within a root path
					if writeEnd.After(rootPathSpan.maxStop) {
						rootPathSpan.maxStop = writeEnd
					}
					if werr != nil {
						rootPathSpan.span.SetStatus(codes.Error, werr.Error())
					}
					rootPathSpan.mu.Unlock()

					if werr != nil {
						return werr
					}

					cachedResultsMu.Lock()
					cachedResults = append(cachedResults, appliedChange)
					only[path] = struct{}{}
					upsertSet[path] = struct{}{}
					cachedResultsMu.Unlock()

					doHandle := cacheCtx != nil
					if local.copyPath != "" {
						path, doHandle = strings.CutPrefix(path, local.copyPath)
					}
					if doHandle {
						relPathFound = true
						applied := appliedChange.result()
						if err := cacheCtx.HandleChange(applied.kind, path, applied.stat, nil); err != nil {
							return fmt.Errorf("failed to handle change in content hasher: %w", err)
						}
					}

					return nil
				})
				return nil
			}

		case ChangeKindDelete:
			deleteCount++
			/*
				Deletes don't have upperStat, so we can't consult GitIgnored directly.

				Example:
				- .gitignore contains "tmp/"
				- mirror previously has tmp/a
				- client deletes tmp/a
				- remote walk includes tmp/ (GitIgnored) but not tmp/a (gone)
				- diff emits a delete for tmp/a

				We skip deletes under ignored prefixes to avoid mutating the shared mirror
				and to keep `only`/conflict tracking consistent with "ignored paths are inert."
			*/
			if isIgnoredPath(path) {
				return nil
			}

			appliedChange, err := local.RemoveAll(egCtx, path)
			if err != nil {
				return err
			}
			cachedResultsMu.Lock()
			cachedResults = append(cachedResults, appliedChange)
			only[path] = struct{}{}
			deleteSet[path] = struct{}{}
			cachedResultsMu.Unlock()
			// no need to apply removals to the cacheCtx since it starts empty every Sync call.
			return nil

		case ChangeKindNone:
			noneCount++
			appliedChange, err := local.GetPreviousChange(egCtx, path, lowerStat)
			if err != nil {
				return err
			}
			cachedResultsMu.Lock()
			cachedResults = append(cachedResults, appliedChange)
			only[path] = struct{}{}
			noneSet[path] = struct{}{}
			cachedResultsMu.Unlock()

			doHandle := cacheCtx != nil
			if local.copyPath != "" {
				path, doHandle = strings.CutPrefix(path, local.copyPath)
			}
			if doHandle {
				relPathFound = true
				applied := appliedChange.result()
				if err := cacheCtx.HandleChange(applied.kind, path, applied.stat, nil); err != nil {
					return fmt.Errorf("failed to handle change in content hasher: %w", err)
				}
			}

			return nil

		default:
			return fmt.Errorf("unsupported change kind: %s", kind)
		}
	})

	if err := eg.Wait(); err != nil {
		diffSpan.RecordError(err)
		diffSpan.SetStatus(codes.Error, err.Error())
		diffSpan.End()
		return nil, err
	}
	for _, hardlink := range hardlinks {
		appliedChange, err := local.Hardlink(ctx, hardlink.kind, hardlink.path, hardlink.upperStat)
		if err != nil {
			diffSpan.RecordError(err)
			diffSpan.SetStatus(codes.Error, err.Error())
			diffSpan.End()
			return nil, err
		}
		cachedResultsMu.Lock()
		cachedResults = append(cachedResults, appliedChange)
		only[hardlink.path] = struct{}{}
		upsertSet[hardlink.path] = struct{}{}
		cachedResultsMu.Unlock()

		doHandle := cacheCtx != nil
		path := hardlink.path
		if local.copyPath != "" {
			path, doHandle = strings.CutPrefix(path, local.copyPath)
		}
		if doHandle {
			relPathFound = true
			applied := appliedChange.result()
			if err := cacheCtx.HandleChange(applied.kind, path, applied.stat, nil); err != nil {
				diffSpan.RecordError(err)
				diffSpan.SetStatus(codes.Error, err.Error())
				diffSpan.End()
				return nil, fmt.Errorf("failed to handle change in content hasher: %w", err)
			}
		}
	}

	if forParents {
		diffSpan.End()
		// we created the parent dirs, nothing else to do now
		return nil, nil
	}
	diffApplyDurationMs := time.Since(diffApplyStart).Milliseconds()
	upsertCount := len(upsertSet)
	deleteSetCount := len(deleteSet)
	noneSetCount := len(noneSet)
	diffSpan.SetAttributes(
		attribute.Int("filesync.change.add", addCount),
		attribute.Int("filesync.change.modify", modifyCount),
		attribute.Int("filesync.change.delete", deleteCount),
		attribute.Int("filesync.change.none", noneCount),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.path.ignored", ignoredPathCount),
		attribute.Int("filesync.change.deferred_hardlink", deferredHardlinkCount),
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
	)
	diffSpan.End()

	filesyncSpan := trace.SpanFromContext(ctx)
	ctx, copySpan := Tracer(ctx).Start(ctx, "copy")
	defer telemetry.EndWithCause(copySpan, &rerr)
	materializeStart := time.Now()
	// TEMPORARY: keep detailed phase tracing until CAS rollout is validated on
	// large-context incremental syncs, then collapse to stable long-term metrics.
	setFilesyncAttrs := func(attrs ...attribute.KeyValue) {
		if filesyncSpan != nil {
			filesyncSpan.SetAttributes(attrs...)
		}
	}
	emitEvent := func(name string, attrs ...attribute.KeyValue) {
		copySpan.AddEvent(name, trace.WithAttributes(attrs...))
	}
	copySpan.SetAttributes(
		attribute.Int("filesync.change.add", addCount),
		attribute.Int("filesync.change.modify", modifyCount),
		attribute.Int("filesync.change.delete", deleteCount),
		attribute.Int("filesync.change.none", noneCount),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.path.only", len(only)),
		attribute.Int("filesync.path.ignored", ignoredPathCount),
		attribute.Int("filesync.change.deferred_hardlink", deferredHardlinkCount),
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
	)
	copySpan.SetAttributes(attribute.Bool("filesync.materialize.parent_based", parentBasedMaterialize))
	if local.scopeKey != "" {
		copySpan.SetAttributes(
			attribute.String("filesync.scope.key", local.scopeKey.String()),
			attribute.Int("filesync.scope.chain_depth.prev", int(scopeHead.ChainDepth)),
			attribute.Int("filesync.scope.chain_depth.cap", int(maxParentMaterializeChainDepth)),
			attribute.Bool("filesync.scope.chain_depth.capped", scopeHeadDepthCapped),
		)
		if scopeHeadDepthCapped {
			emitEvent("filesync.scope.chain_depth.capped", []attribute.KeyValue{
				attribute.Int("filesync.scope.chain_depth.prev", int(scopeHead.ChainDepth)),
				attribute.Int("filesync.scope.chain_depth.cap", int(maxParentMaterializeChainDepth)),
			}...)
		}
	}
	persistScopeHead := func(ref bkcache.ImmutableRef, rootDigest digest.Digest, materialized bool) {
		if local.scopeKey == "" || ref == nil {
			return
		}

		prevGeneration := uint64(0)
		prevDepth := uint32(0)
		if scopeHeadFound {
			prevGeneration = scopeHead.Generation
			prevDepth = scopeHead.ChainDepth
		}
		nextDepth := uint32(1)
		switch {
		case !materialized && scopeHeadFound && scopeHead.RootDigest == rootDigest:
			nextDepth = scopeHead.ChainDepth
		case materialized && parentBasedMaterialize && prevDepth > 0:
			nextDepth = prevDepth + 1
		}

		head := cas.ScopeHead{
			Scope:         local.scopeKey,
			RootDigest:    rootDigest,
			MaterialRefID: ref.ID(),
			Generation:    prevGeneration + 1,
			ChainDepth:    nextDepth,
		}
		scopeHeadStore := cas.ScopeHeadStore{Store: cacheManager}
		if err := scopeHeadStore.Save(ctx, ref, head, prevGeneration); err != nil {
			bklog.G(ctx).Warnf("failed to save filesync scope head for %q: %v", local.scopeKey, err)
		}
		scopeHead = head
		scopeHeadFound = true
	}

	// If we didn't find any files/dir in the given relative path, we can early return an error.
	if local.copyPath != "" && !relPathFound {
		return nil, fmt.Errorf("%s: no such file or directory", local.copyPath)
	}

	checksumCtx, checksumSpan := Tracer(ctx).Start(ctx, "filesync.checksum")
	checksumStart := time.Now()
	dgst, err := cacheCtx.Checksum(checksumCtx, newCopyRef, "/", bkcontenthash.ChecksumOpts{}, session)
	if err != nil {
		checksumSpan.RecordError(err)
		checksumSpan.SetStatus(codes.Error, err.Error())
		checksumSpan.End()
		return nil, fmt.Errorf("failed to checksum: %w", err)
	}
	checksumDurationMs := time.Since(checksumStart).Milliseconds()
	checksumSpan.SetAttributes(
		attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
		attribute.String("filesync.checksum.digest", dgst.String()),
	)
	checksumSpan.End()
	copySpan.SetAttributes(attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs))

	// If we have already created a cache ref with the same content hash, use that instead of copying
	// another equivalent one.
	searchCtx, searchSpan := Tracer(ctx).Start(ctx, "filesync.search_contenthash")
	searchStart := time.Now()
	sis, err := contenthash.SearchContentHash(searchCtx, cacheManager, dgst)
	if err != nil {
		searchSpan.RecordError(err)
		searchSpan.SetStatus(codes.Error, err.Error())
		searchSpan.End()
		return nil, fmt.Errorf("failed to search content hash: %w", err)
	}
	searchDurationMs := time.Since(searchStart).Milliseconds()
	searchSpan.SetAttributes(
		attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
		attribute.Int("filesync.contenthash.candidates", len(sis)),
	)
	searchSpan.End()
	copySpan.SetAttributes(attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs))
	for _, si := range sis {
		finalRef, err := cacheManager.Get(ctx, si.ID(), nil)
		if err == nil {
			copySpan.SetAttributes(
				attribute.Bool("filesync.contenthash.hit", true),
				attribute.Int("filesync.contenthash.candidates", len(sis)),
			)
			materializeDurationMs := time.Since(materializeStart).Milliseconds()
			copySpan.SetAttributes(attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs))
			setFilesyncAttrs(
				attribute.Bool("filesync.contenthash.hit", true),
				attribute.Int("filesync.path.only", len(only)),
				attribute.Int("filesync.delta.upsert", upsertCount),
				attribute.Int("filesync.delta.delete", deleteSetCount),
				attribute.Int("filesync.delta.none", noneSetCount),
				attribute.Int("filesync.change.add", addCount),
				attribute.Int("filesync.change.modify", modifyCount),
				attribute.Int("filesync.change.delete", deleteCount),
				attribute.Int("filesync.change.none", noneCount),
				attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
				attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
				attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
				attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs),
				attribute.String("filesync.checksum.digest", dgst.String()),
			)
			emitEvent("filesync.contenthash.hit", []attribute.KeyValue{
				attribute.Int("filesync.change.add", addCount),
				attribute.Int("filesync.change.modify", modifyCount),
				attribute.Int("filesync.change.delete", deleteCount),
				attribute.Int("filesync.change.none", noneCount),
				attribute.Int("filesync.delta.upsert", upsertCount),
				attribute.Int("filesync.delta.delete", deleteSetCount),
				attribute.Int("filesync.delta.none", noneSetCount),
				attribute.Int("filesync.path.only", len(only)),
				attribute.Int("filesync.path.ignored", ignoredPathCount),
				attribute.Int("filesync.change.deferred_hardlink", deferredHardlinkCount),
				attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
				attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
				attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
				attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs),
				attribute.String("filesync.checksum.digest", dgst.String()),
			}...,
			)
			bklog.G(ctx).Debugf("reusing copy ref %s", si.ID())
			persistScopeHead(finalRef, dgst, false)
			return finalRef, nil
		} else {
			bklog.G(ctx).Debugf("failed to get cache ref: %v", err)
		}
	}
	copySpan.SetAttributes(
		attribute.Bool("filesync.contenthash.hit", false),
		attribute.Int("filesync.contenthash.candidates", len(sis)),
	)
	setFilesyncAttrs(
		attribute.Bool("filesync.contenthash.hit", false),
		attribute.Int("filesync.path.only", len(only)),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.change.add", addCount),
		attribute.Int("filesync.change.modify", modifyCount),
		attribute.Int("filesync.change.delete", deleteCount),
		attribute.Int("filesync.change.none", noneCount),
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
		attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
		attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
		attribute.String("filesync.checksum.digest", dgst.String()),
	)
	emitEvent("filesync.contenthash.miss", []attribute.KeyValue{
		attribute.Int("filesync.change.add", addCount),
		attribute.Int("filesync.change.modify", modifyCount),
		attribute.Int("filesync.change.delete", deleteCount),
		attribute.Int("filesync.change.none", noneCount),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.path.only", len(only)),
		attribute.Int("filesync.path.ignored", ignoredPathCount),
		attribute.Int("filesync.change.deferred_hardlink", deferredHardlinkCount),
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
		attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
		attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
		attribute.String("filesync.checksum.digest", dgst.String()),
	}...,
	)

	copyRefMntable, err := newCopyRef.Mount(ctx, false, session)
	if err != nil {
		return nil, fmt.Errorf("failed to get mountable: %w", err)
	}
	copyRefMnter := snapshot.LocalMounter(copyRefMntable)
	copyRefMntPath, err := copyRefMnter.Mount()
	if err != nil {
		return nil, fmt.Errorf("failed to mount: %w", err)
	}
	defer func() {
		if copyRefMnter != nil {
			if err := copyRefMnter.Unmount(); err != nil {
				rerr = errors.Join(rerr, fmt.Errorf("failed to unmount: %w", err))
			}
		}
	}()

	copyOnly := only
	if parentBasedMaterialize {
		copyOnly = expandCopyOnlySet(upsertSet)
	}
	deleteTargets := make([]string, 0, len(deleteSet))
	if parentBasedMaterialize {
		deleteTargets = projectDeleteTargets(deleteSet, local.copyPath)
	}
	copySpan.SetAttributes(
		attribute.Int("filesync.path.copy_only", len(copyOnly)),
		attribute.Int("filesync.path.delete_targets", len(deleteTargets)),
	)

	if parentBasedMaterialize {
		for _, relDeletePath := range deleteTargets {
			if err := removeProjectedPath(copyRefMntPath, relDeletePath); err != nil {
				return nil, fmt.Errorf("failed to apply delete %q: %w", relDeletePath, err)
			}
		}
	}

	copyOpts := []fscopy.Opt{
		func(ci *fscopy.CopyInfo) {
			// only copy files that we know about changes for
			ci.Only = copyOnly
			ci.CopyDirContents = true
			ci.BaseCopyPath = local.copyPath
		},
		fscopy.WithXAttrErrorHandler(func(dst, src, key string, err error) error {
			bklog.G(ctx).Debugf("xattr error during local import copy: %v", err)
			return nil
		}),
	}

	copyCtx, copyDataSpan := Tracer(ctx).Start(ctx, "filesync.copy_data")
	var copyDurationMs int64
	if len(copyOnly) > 0 {
		copyStart := time.Now()
		if err := fscopy.Copy(copyCtx,
			local.rootPath,
			filepath.Join(local.subdir, local.copyPath),
			copyRefMntPath, "/",
			copyOpts...,
		); err != nil {
			copyDataSpan.RecordError(err)
			copyDataSpan.SetStatus(codes.Error, err.Error())
			copyDataSpan.End()
			return nil, fmt.Errorf("failed to copy %q: %w", local.subdir, err)
		}
		copyDurationMs = time.Since(copyStart).Milliseconds()
	}
	copyDataSpan.SetAttributes(
		attribute.Int64("filesync.copy.duration_ms", copyDurationMs),
		attribute.Int("filesync.path.only", len(copyOnly)),
		attribute.String("filesync.checksum.digest", dgst.String()),
	)
	copyDataSpan.End()
	copySpan.SetAttributes(attribute.Int64("filesync.copy.duration_ms", copyDurationMs))
	emitEvent("filesync.copy.finished", []attribute.KeyValue{
		attribute.Int64("filesync.copy.duration_ms", copyDurationMs),
		attribute.Int("filesync.path.only", len(copyOnly)),
		attribute.String("filesync.checksum.digest", dgst.String()),
	}...,
	)

	if err := copyRefMnter.Unmount(); err != nil {
		copyRefMnter = nil
		return nil, fmt.Errorf("failed to unmount: %w", err)
	}
	copyRefMnter = nil

	commitCtx, commitSpan := Tracer(ctx).Start(ctx, "filesync.commit")
	commitStart := time.Now()
	finalRef, err := newCopyRef.Commit(commitCtx)
	if err != nil {
		commitSpan.RecordError(err)
		commitSpan.SetStatus(codes.Error, err.Error())
		commitSpan.End()
		return nil, fmt.Errorf("failed to commit: %w", err)
	}
	commitDurationMs := time.Since(commitStart).Milliseconds()
	commitSpan.SetAttributes(attribute.Int64("filesync.commit.duration_ms", commitDurationMs))
	commitSpan.End()
	copySpan.SetAttributes(attribute.Int64("filesync.commit.duration_ms", commitDurationMs))
	defer func() {
		if rerr != nil {
			if finalRef != nil {
				ctx := context.WithoutCancel(ctx)
				if err := finalRef.Release(ctx); err != nil {
					rerr = errors.Join(rerr, fmt.Errorf("failed to release: %w", err))
				}
			}
		}
	}()

	finalizeCtx, finalizeSpan := Tracer(ctx).Start(ctx, "filesync.finalize")
	finalizeStart := time.Now()
	if err := finalRef.Finalize(finalizeCtx); err != nil {
		finalizeSpan.RecordError(err)
		finalizeSpan.SetStatus(codes.Error, err.Error())
		finalizeSpan.End()
		return nil, fmt.Errorf("failed to finalize: %w", err)
	}
	finalizeDurationMs := time.Since(finalizeStart).Milliseconds()
	finalizeSpan.SetAttributes(attribute.Int64("filesync.finalize.duration_ms", finalizeDurationMs))
	finalizeSpan.End()
	copySpan.SetAttributes(attribute.Int64("filesync.finalize.duration_ms", finalizeDurationMs))

	// FIXME: when the ID of the ref given to SetCacheContext is different from the ID of the
	// ref the cacheCtx was created with, buildkit just stores it in a in-memory LRU that's
	// only hit by some code paths. This is probably a bug. To coerce it into actually storing
	// the cacheCtx on finalRef, we have to do this little dance of setting it (so it's in the LRU)
	// and then getting it+setting again.
	if err := bkcontenthash.SetCacheContext(ctx, finalRef, cacheCtx); err != nil {
		return nil, fmt.Errorf("failed to set cache context: %w", err)
	}
	cacheCtx, err = bkcontenthash.GetCacheContext(ctx, finalRef)
	if err != nil {
		return nil, fmt.Errorf("failed to get cache context: %w", err)
	}
	if err := bkcontenthash.SetCacheContext(ctx, finalRef, cacheCtx); err != nil {
		return nil, fmt.Errorf("failed to set cache context: %w", err)
	}

	if err := (contenthash.CacheRefMetadata{RefMetadata: finalRef}).SetContentHashKey(dgst); err != nil {
		return nil, fmt.Errorf("failed to set content hash key: %w", err)
	}
	if err := finalRef.SetDescription(fmt.Sprintf("local dir %s (include: %v) (exclude %v)", local.subdir, local.includes, local.excludes)); err != nil {
		return nil, fmt.Errorf("failed to set description: %w", err)
	}

	if err := finalRef.SetCachePolicyRetain(); err != nil {
		return nil, fmt.Errorf("failed to set cache policy: %w", err)
	}
	// NOTE: this MUST be released after setting cache policy retain or bk cache manager decides to
	// remove finalRef...
	if err := newCopyRef.Release(ctx); err != nil {
		newCopyRef = nil
		return nil, fmt.Errorf("failed to release: %w", err)
	}
	newCopyRef = nil
	persistScopeHead(finalRef, dgst, true)
	materializeDurationMs := time.Since(materializeStart).Milliseconds()
	copySpan.SetAttributes(attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs))
	setFilesyncAttrs(
		attribute.Bool("filesync.contenthash.hit", false),
		attribute.Int("filesync.path.only", len(only)),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.change.add", addCount),
		attribute.Int("filesync.change.modify", modifyCount),
		attribute.Int("filesync.change.delete", deleteCount),
		attribute.Int("filesync.change.none", noneCount),
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
		attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
		attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
		attribute.Int64("filesync.copy.duration_ms", copyDurationMs),
		attribute.Int64("filesync.commit.duration_ms", commitDurationMs),
		attribute.Int64("filesync.finalize.duration_ms", finalizeDurationMs),
		attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs),
		attribute.String("filesync.checksum.digest", dgst.String()),
	)
	emitEvent("filesync.materialize.finished", []attribute.KeyValue{
		attribute.Int64("filesync.diff_apply.duration_ms", diffApplyDurationMs),
		attribute.Int64("filesync.checksum.duration_ms", checksumDurationMs),
		attribute.Int64("filesync.search_contenthash.duration_ms", searchDurationMs),
		attribute.Int64("filesync.copy.duration_ms", copyDurationMs),
		attribute.Int64("filesync.commit.duration_ms", commitDurationMs),
		attribute.Int64("filesync.finalize.duration_ms", finalizeDurationMs),
		attribute.Int64("filesync.materialize.duration_ms", materializeDurationMs),
		attribute.Int("filesync.delta.upsert", upsertCount),
		attribute.Int("filesync.delta.delete", deleteSetCount),
		attribute.Int("filesync.delta.none", noneSetCount),
		attribute.Int("filesync.path.only", len(only)),
		attribute.String("filesync.checksum.digest", dgst.String()),
	}...,
	)

	return finalRef, nil
}

func expandCopyOnlySet(paths map[string]struct{}) map[string]struct{} {
	out := make(map[string]struct{}, len(paths))
	for rawPath := range paths {
		path := filepath.Clean(rawPath)
		for path != "." && path != string(os.PathSeparator) && path != "" {
			if _, ok := out[path]; ok {
				break
			}
			out[path] = struct{}{}
			next := filepath.Dir(path)
			if next == path {
				break
			}
			path = next
		}
	}
	return out
}

func shouldUseParentFromScopeHead(head cas.ScopeHead) bool {
	return head.ChainDepth < maxParentMaterializeChainDepth
}

func projectDeleteTargets(deleteSet map[string]struct{}, copyPath string) []string {
	targetSet := make(map[string]struct{}, len(deleteSet))
	for rawPath := range deleteSet {
		relPath := rawPath
		if copyPath != "" {
			var ok bool
			relPath, ok = strings.CutPrefix(relPath, copyPath)
			if !ok {
				continue
			}
		}
		relPath = strings.TrimPrefix(relPath, string(os.PathSeparator))
		relPath = strings.TrimPrefix(relPath, "/")
		relPath = filepath.Clean(relPath)
		if relPath == "" {
			relPath = "."
		}
		targetSet[relPath] = struct{}{}
	}

	targets := make([]string, 0, len(targetSet))
	for target := range targetSet {
		targets = append(targets, target)
	}
	sort.Slice(targets, func(i, j int) bool {
		depthI := strings.Count(targets[i], string(os.PathSeparator))
		depthJ := strings.Count(targets[j], string(os.PathSeparator))
		if depthI == depthJ {
			return targets[i] < targets[j]
		}
		return depthI > depthJ
	})
	return targets
}

func removeProjectedPath(root, relPath string) error {
	if relPath == "." {
		entries, err := os.ReadDir(root)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			if err := os.RemoveAll(filepath.Join(root, entry.Name())); err != nil {
				return err
			}
		}
		return nil
	}

	normalizedRelPath, err := cas.NormalizeEntryPath(relPath)
	if err != nil {
		return err
	}

	target, err := cfs.RootPath(root, filepath.Join("/", normalizedRelPath))
	if err != nil {
		return err
	}
	return os.RemoveAll(target)
}

// the full absolute path on the local filesystem
func (local *localFS) toFullPath(path string) string {
	return filepath.Join(local.rootPath, local.subdir, path)
}

// the absolute path under local.rootPath
func (local *localFS) toRootPath(path string) string {
	return filepath.Join(local.subdir, path)
}

// the cache key to use for an operation on a given path (where path is relative to local.subdir)
func (local *localFS) cacheKey(path string) string {
	return local.toRootPath(path)
}

// GetPreviousChange is called when the differ identifies that our cache and the client's filesystem match at this path.
// We still need to put this into the cacheCtx object we are accumulating so that the path contributes to the content
// hash.
//
// For non-regular files (dirs, symlinks, etc.) we just base the hash on the stat, which we already have from the differ.
//
// For regular files, we also need to include the content hash of the file contents, which would be expensive to re-run.
// Instead, the WriteFile method stores the hash in an xattr, which we just read here.
//
// Unlike other methods below, we don't need to verifyExpectedChange since there was no change applied to the path.
func (local *localFS) GetPreviousChange(ctx context.Context, path string, stat *types.Stat) (CachedChange, error) {
	return local.changeCache.getOrInit(ctx, local.cacheKey(path), func(_ context.Context) (*ChangeWithStat, error) {
		fullPath := local.toFullPath(path)

		isRegular := stat.Mode&uint32(os.ModeType) == 0
		if isRegular {
			dgstBytes, err := sysx.Getxattr(fullPath, hashXattrKey)
			if err != nil {
				return nil, fmt.Errorf("failed to get content hash xattr: %w", err)
			}
			return &ChangeWithStat{
				kind: ChangeKindNone,
				stat: &HashedStatInfo{
					StatInfo: StatInfo{stat},
					dgst:     digest.Digest(dgstBytes),
				},
			}, nil
		}

		return &ChangeWithStat{
			kind: ChangeKindNone,
			stat: &HashedStatInfo{
				StatInfo: StatInfo{stat},
				dgst:     digest.NewDigest(hashutil.XXH3, newHashFromStat(stat)),
			},
		}, nil
	})
}

func (local *localFS) RemoveAll(ctx context.Context, path string) (CachedChange, error) {
	appliedChange, err := local.changeCache.getOrInit(ctx, local.cacheKey(path), func(ctx context.Context) (*ChangeWithStat, error) {
		fullPath := local.toFullPath(path)
		if err := os.RemoveAll(fullPath); err != nil {
			return nil, err
		}
		return &ChangeWithStat{kind: ChangeKindDelete}, nil
	})
	if err != nil {
		return nil, err
	}

	if err := verifyExpectedChange(path, appliedChange.result(), ChangeKindDelete, nil); err != nil {
		appliedChange.release()
		return nil, err
	}
	return appliedChange, nil
}

func (local *localFS) Mkdir(ctx context.Context, expectedChangeKind ChangeKind, path string, upperStat *types.Stat) (CachedChange, error) {
	appliedChange, err := local.changeCache.getOrInit(ctx, local.cacheKey(path), func(ctx context.Context) (*ChangeWithStat, error) {
		fullPath := local.toFullPath(path)

		lowerStat, err := os.Lstat(fullPath)
		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("failed to stat existing path: %w", err)
		}

		isNewDir := lowerStat == nil
		replacesNonDir := lowerStat != nil && !lowerStat.IsDir()

		if replacesNonDir {
			if err := os.Remove(fullPath); err != nil {
				return nil, fmt.Errorf("failed to remove existing file: %w", err)
			}
		}

		if isNewDir || replacesNonDir {
			if err := os.Mkdir(fullPath, os.FileMode(upperStat.Mode)&os.ModePerm); err != nil {
				return nil, fmt.Errorf("failed to create directory: %w", err)
			}
		}

		if err := rewriteMetadata(fullPath, upperStat); err != nil {
			return nil, fmt.Errorf("failed to rewrite directory metadata: %w", err)
		}

		return &ChangeWithStat{
			kind: expectedChangeKind,
			stat: &HashedStatInfo{
				StatInfo: StatInfo{upperStat},
				dgst:     digest.NewDigest(hashutil.XXH3, newHashFromStat(upperStat)),
			},
		}, nil
	})
	if err != nil {
		return nil, err
	}

	if err := verifyExpectedChange(path, appliedChange.result(), expectedChangeKind, upperStat); err != nil {
		appliedChange.release()
		return nil, err
	}
	return appliedChange, nil
}

func (local *localFS) Symlink(ctx context.Context, expectedChangeKind ChangeKind, path string, upperStat *types.Stat) (CachedChange, error) {
	appliedChange, err := local.changeCache.getOrInit(ctx, local.cacheKey(path), func(ctx context.Context) (*ChangeWithStat, error) {
		fullPath := local.toFullPath(path)

		lowerStat, err := os.Lstat(fullPath)
		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("failed to stat existing path: %w", err)
		}

		isNewSymlink := lowerStat == nil

		if !isNewSymlink {
			if err := os.RemoveAll(fullPath); err != nil {
				return nil, fmt.Errorf("failed to remove existing file: %w", err)
			}
		}

		if err := os.Symlink(upperStat.Linkname, fullPath); err != nil {
			return nil, fmt.Errorf("failed to create symlink: %w", err)
		}

		return &ChangeWithStat{
			kind: expectedChangeKind,
			stat: &HashedStatInfo{
				StatInfo: StatInfo{upperStat},
				dgst:     digest.NewDigest(hashutil.XXH3, newHashFromStat(upperStat)),
			},
		}, nil
	})
	if err != nil {
		return nil, err
	}

	if err := verifyExpectedChange(path, appliedChange.result(), expectedChangeKind, upperStat); err != nil {
		appliedChange.release()
		return nil, err
	}
	return appliedChange, nil
}

func (local *localFS) Hardlink(ctx context.Context, expectedChangeKind ChangeKind, path string, upperStat *types.Stat) (CachedChange, error) {
	appliedChange, err := local.changeCache.getOrInit(ctx, local.cacheKey(path), func(ctx context.Context) (*ChangeWithStat, error) {
		fullPath := local.toFullPath(path)

		lowerStat, err := os.Lstat(fullPath)
		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("failed to stat existing path: %w", err)
		}

		replacesExisting := lowerStat != nil

		if replacesExisting {
			if err := os.RemoveAll(fullPath); err != nil {
				return nil, fmt.Errorf("failed to remove existing file: %w", err)
			}
		}

		if err := os.Link(local.toFullPath(upperStat.Linkname), fullPath); err != nil {
			return nil, fmt.Errorf("failed to create hardlink: %w", err)
		}

		return &ChangeWithStat{
			kind: expectedChangeKind,
			stat: &HashedStatInfo{
				StatInfo: StatInfo{upperStat},
				dgst:     digest.NewDigest(hashutil.XXH3, newHashFromStat(upperStat)),
			},
		}, nil
	})
	if err != nil {
		return nil, err
	}

	if err := verifyExpectedChange(path, appliedChange.result(), expectedChangeKind, upperStat); err != nil {
		appliedChange.release()
		return nil, err
	}
	return appliedChange, nil
}

var copyBufferPool = &sync.Pool{
	New: func() any {
		buffer := make([]byte, 32*1024) // same size that fsutil.Send chunks files into
		return &buffer
	},
}

func (local *localFS) WriteFile(ctx context.Context, expectedChangeKind ChangeKind, path string, upperStat *types.Stat, upperFS ReadFS) (CachedChange, int64, error) {
	var writtenBytes int64
	appliedChange, err := local.changeCache.getOrInit(ctx, local.cacheKey(path), func(ctx context.Context) (*ChangeWithStat, error) {
		reader, err := upperFS.ReadFile(ctx, path)
		if err != nil {
			return nil, fmt.Errorf("failed to read file %q: %w", path, err)
		}
		defer reader.Close()

		fullPath := local.toFullPath(path)

		lowerStat, err := os.Lstat(fullPath)
		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("failed to stat existing path: %w", err)
		}

		replacesExisting := lowerStat != nil

		if replacesExisting {
			if err := os.RemoveAll(fullPath); err != nil {
				return nil, fmt.Errorf("failed to remove existing file: %w", err)
			}
		}

		f, err := os.OpenFile(fullPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, os.FileMode(upperStat.Mode)&os.ModePerm)
		if err != nil {
			return nil, err
		}
		defer f.Close()

		h := newHashFromStat(upperStat)

		copyBuf := copyBufferPool.Get().(*[]byte)
		written, err := io.CopyBuffer(io.MultiWriter(f, h), reader, *copyBuf)
		writtenBytes = written
		copyBufferPool.Put(copyBuf)
		if err != nil {
			return nil, fmt.Errorf("failed to copy contents: %w", err)
		}
		if err := f.Close(); err != nil {
			return nil, fmt.Errorf("failed to close file: %w", err)
		}

		if err := rewriteMetadata(fullPath, upperStat); err != nil {
			return nil, fmt.Errorf("failed to rewrite file metadata: %w", err)
		}

		// store the hash in an xattr so GetPreviousChange above can use that instead of re-hashing the file
		dgst := digest.NewDigest(hashutil.XXH3, h)
		if err := sysx.Setxattr(fullPath, hashXattrKey, []byte(dgst.String()), 0); err != nil {
			return nil, fmt.Errorf("failed to set content hash xattr: %w", err)
		}

		return &ChangeWithStat{
			kind: expectedChangeKind,
			stat: &HashedStatInfo{
				StatInfo: StatInfo{upperStat},
				dgst:     dgst,
			},
		}, nil
	})
	if err != nil {
		return nil, 0, err
	}

	if err := verifyExpectedChange(path, appliedChange.result(), expectedChangeKind, upperStat); err != nil {
		appliedChange.release()
		return nil, 0, err
	}
	return appliedChange, writtenBytes, nil
}

func (local *localFS) Walk(ctx context.Context, path string, walkFn fs.WalkDirFunc) error {
	return local.filterFS.Walk(ctx, path, walkFn)
}

func rewriteMetadata(p string, upperStat *types.Stat) error {
	for key, value := range upperStat.Xattrs {
		sysx.Setxattr(p, key, value, 0)
	}

	if err := os.Lchown(p, int(upperStat.Uid), int(upperStat.Gid)); err != nil {
		return fmt.Errorf("failed to change owner: %w", err)
	}

	if os.FileMode(upperStat.Mode)&os.ModeSymlink == 0 {
		if err := os.Chmod(p, os.FileMode(upperStat.Mode)); err != nil {
			return fmt.Errorf("failed to change mode: %w", err)
		}
	}

	var utimes [2]unix.Timespec
	utimes[0] = unix.NsecToTimespec(upperStat.ModTime)
	utimes[1] = utimes[0]

	if err := unix.UtimesNanoAt(unix.AT_FDCWD, p, utimes[0:], unix.AT_SYMLINK_NOFOLLOW); err != nil {
		return fmt.Errorf("failed to call utimes: %w", err)
	}

	return nil
}

// Check that the change applied by mutating methods is actually the one we thought we were applying. If not, the client
// filesystem changed during the sync and we need to error out to avoid inconsistencies.
func verifyExpectedChange(path string, appliedChange *ChangeWithStat, expectedKind ChangeKind, expectedStat *types.Stat) error {
	if appliedChange.kind == ChangeKindDelete || expectedKind == ChangeKindDelete {
		if appliedChange.kind != expectedKind {
			return &ErrConflict{Path: path, FieldName: "change kind", OldVal: changeKindString(appliedChange.kind), NewVal: expectedKind.String()}
		}
		// nothing else to compare for deletes
		return nil
	}

	if uint32(appliedChange.stat.Mode()) != expectedStat.Mode {
		return &ErrConflict{Path: path, FieldName: "mode", OldVal: fmt.Sprintf("%o", appliedChange.stat.Mode()), NewVal: fmt.Sprintf("%o", expectedStat.Mode)}
	}
	if appliedChange.stat.Uid != expectedStat.Uid {
		return &ErrConflict{Path: path, FieldName: "uid", OldVal: fmt.Sprintf("%d", appliedChange.stat.Uid), NewVal: fmt.Sprintf("%d", expectedStat.Uid)}
	}
	if appliedChange.stat.Gid != expectedStat.Gid {
		return &ErrConflict{Path: path, FieldName: "gid", OldVal: fmt.Sprintf("%d", appliedChange.stat.Gid), NewVal: fmt.Sprintf("%d", expectedStat.Gid)}
	}
	if appliedChange.stat.Size_ != expectedStat.Size_ {
		return &ErrConflict{Path: path, FieldName: "size", OldVal: fmt.Sprintf("%d", appliedChange.stat.Size()), NewVal: fmt.Sprintf("%d", expectedStat.Size_)}
	}
	if appliedChange.stat.Devmajor != expectedStat.Devmajor {
		return &ErrConflict{Path: path, FieldName: "devmajor", OldVal: fmt.Sprintf("%d", appliedChange.stat.Devmajor), NewVal: fmt.Sprintf("%d", expectedStat.Devmajor)}
	}
	if appliedChange.stat.Devminor != expectedStat.Devminor {
		return &ErrConflict{Path: path, FieldName: "devminor", OldVal: fmt.Sprintf("%d", appliedChange.stat.Devminor), NewVal: fmt.Sprintf("%d", expectedStat.Devminor)}
	}

	// Only compare link name when it's a symlink, not a hardlink. For hardlinks, whether the Linkname field
	// is set depends on whether or not the source of the link was included in the sync, which can vary between
	// different include/exclude settings on the same dir.
	if appliedChange.stat.Mode()&os.ModeType == os.ModeSymlink {
		if appliedChange.stat.Linkname != expectedStat.Linkname {
			return &ErrConflict{Path: path, FieldName: "linkname", OldVal: appliedChange.stat.Linkname, NewVal: expectedStat.Linkname}
		}
	}

	// Match the differ logic by only comparing modtime for regular files (as a heuristic to
	// expensive avoid content comparisons for every file that appears in a diff, using the
	// modtime as a proxy instead).
	//
	// We don't want to compare modtimes for directories right now since we explicitly don't
	// attempt to reset parent dir modtimes when a dirent is synced in or removed.
	if appliedChange.stat.Mode().IsRegular() {
		if appliedChange.stat.ModTime().UnixNano() != expectedStat.ModTime {
			return &ErrConflict{Path: path, FieldName: "mod time", OldVal: fmt.Sprintf("%d", appliedChange.stat.ModTime().UnixNano()), NewVal: fmt.Sprintf("%d", expectedStat.ModTime)}
		}
	}

	return nil
}

type ErrConflict struct {
	Path      string
	FieldName string
	OldVal    string
	NewVal    string
}

func (e *ErrConflict) Error() string {
	return fmt.Sprintf("conflict at %q: %s changed from %q to %q during sync", e.Path, e.FieldName, e.OldVal, e.NewVal)
}
