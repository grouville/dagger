package core

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	bkclient "github.com/dagger/dagger/internal/buildkit/client"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
)

// CacheVolume is a persistent volume with a globally scoped identifier.
type CacheVolume struct {
	Key       string
	Namespace string
	Source    dagql.Optional[DirectoryID]
	Sharing   CacheSharingMode
	Owner     string

	mu        sync.Mutex
	snapshots []*cacheVolumeSnapshot
	selector  string
}

type cacheVolumeSnapshot struct {
	ref    bkcache.MutableRef
	active bool
}

type CacheVolumeMount struct {
	Ref      bkcache.MutableRef
	Selector string

	releaseOnce sync.Once
	releaseErr  error
	release     func(context.Context) error
}

func (mount *CacheVolumeMount) Release(ctx context.Context) error {
	if mount == nil || mount.release == nil {
		return nil
	}
	mount.releaseOnce.Do(func() {
		mount.releaseErr = mount.release(ctx)
	})
	return mount.releaseErr
}

func (*CacheVolume) Type() *ast.Type {
	return &ast.Type{
		NamedType: "CacheVolume",
		NonNull:   true,
	}
}

func (*CacheVolume) TypeDescription() string {
	return "A directory whose contents persist across runs."
}

func NewCache(
	key string,
	namespace string,
	source dagql.Optional[DirectoryID],
	sharing CacheSharingMode,
	owner string,
) *CacheVolume {
	return &CacheVolume{
		Key:       key,
		Namespace: namespace,
		Source:    source,
		Sharing:   sharing,
		Owner:     owner,
	}
}

var _ dagql.OnReleaser = (*CacheVolume)(nil)

func (cache *CacheVolume) OnRelease(ctx context.Context) error {
	cache.mu.Lock()
	defer cache.mu.Unlock()

	var rerr error
	for _, snapshot := range cache.snapshots {
		if snapshot == nil || snapshot.ref == nil {
			continue
		}
		rerr = errors.Join(rerr, snapshot.ref.Release(ctx))
	}
	cache.snapshots = nil
	return rerr
}

func (cache *CacheVolume) getSnapshot() bkcache.MutableRef {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if len(cache.snapshots) == 0 || cache.snapshots[0] == nil {
		return nil
	}
	return cache.snapshots[0].ref
}

func (cache *CacheVolume) getSnapshotSelector() string {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if cache.selector == "" {
		return "/"
	}
	return cache.selector
}

func (cache *CacheVolume) CacheUsageSize(ctx context.Context, identity string) (int64, bool, error) {
	cache.mu.Lock()
	snapshots := append([]*cacheVolumeSnapshot(nil), cache.snapshots...)
	cache.mu.Unlock()
	for _, snapshot := range snapshots {
		if snapshot == nil || snapshot.ref == nil || snapshot.ref.SnapshotID() != identity {
			continue
		}
		size, err := snapshot.ref.Size(ctx)
		if err != nil {
			return 0, false, err
		}
		return size, true, nil
	}
	return 0, false, nil
}

func (cache *CacheVolume) CacheUsageIdentities() []string {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if len(cache.snapshots) == 0 {
		return nil
	}
	identities := make([]string, 0, len(cache.snapshots))
	for _, snapshot := range cache.snapshots {
		if snapshot == nil || snapshot.ref == nil {
			continue
		}
		identities = append(identities, snapshot.ref.SnapshotID())
	}
	return identities
}

func (cache *CacheVolume) PersistedSnapshotRefLinks() []dagql.PersistedSnapshotRefLink {
	cache.mu.Lock()
	defer cache.mu.Unlock()

	if len(cache.snapshots) == 0 {
		return nil
	}
	links := make([]dagql.PersistedSnapshotRefLink, 0, len(cache.snapshots))
	for i, snapshot := range cache.snapshots {
		if snapshot == nil || snapshot.ref == nil {
			continue
		}
		links = append(links, dagql.PersistedSnapshotRefLink{
			RefKey: snapshot.ref.SnapshotID(),
			Role:   cacheVolumeSnapshotRole(i),
		})
	}
	return links
}

func cacheVolumeSnapshotRole(i int) string {
	return "snapshot/" + strconv.Itoa(i)
}

func cacheVolumeSnapshotRoleIndex(role string) (int, bool) {
	index, ok := strings.CutPrefix(role, "snapshot/")
	if !ok {
		return 0, false
	}
	i, err := strconv.Atoi(index)
	if err != nil || i < 0 {
		return 0, false
	}
	return i, true
}

type persistedCacheVolumePayload struct {
	Key       string           `json:"key"`
	Namespace string           `json:"namespace,omitempty"`
	SourceID  string           `json:"sourceID,omitempty"`
	Sharing   CacheSharingMode `json:"sharing,omitempty"`
	Owner     string           `json:"owner,omitempty"`
	Selector  string           `json:"selector,omitempty"`
}

func (cache *CacheVolume) EncodePersistedObject(ctx context.Context, persistedCache dagql.PersistedObjectCache) (json.RawMessage, error) {
	_ = ctx
	_ = persistedCache
	if cache == nil {
		return nil, fmt.Errorf("encode persisted cache volume: nil cache volume")
	}
	sourceID := ""
	if cache.Source.Valid {
		encoded, err := cache.Source.Value.Encode()
		if err != nil {
			return nil, fmt.Errorf("encode persisted cache volume source: %w", err)
		}
		sourceID = encoded
	}
	payload, err := json.Marshal(persistedCacheVolumePayload{
		Key:       cache.Key,
		Namespace: cache.Namespace,
		SourceID:  sourceID,
		Sharing:   cache.Sharing,
		Owner:     cache.Owner,
		Selector:  cache.getSnapshotSelector(),
	})
	if err != nil {
		return nil, fmt.Errorf("marshal persisted cache volume payload: %w", err)
	}
	return payload, nil
}

func (*CacheVolume) DecodePersistedObject(ctx context.Context, dag *dagql.Server, resultID uint64, _ *dagql.ResultCall, payload json.RawMessage) (dagql.Typed, error) {
	var persisted persistedCacheVolumePayload
	if err := json.Unmarshal(payload, &persisted); err != nil {
		return nil, fmt.Errorf("decode persisted cache volume payload: %w", err)
	}

	source := dagql.Optional[DirectoryID]{}
	if persisted.SourceID != "" {
		var sourceID DirectoryID
		if err := sourceID.Decode(persisted.SourceID); err != nil {
			return nil, fmt.Errorf("decode persisted cache volume source: %w", err)
		}
		source = dagql.Optional[DirectoryID]{
			Valid: true,
			Value: sourceID,
		}
	}

	cache := NewCache(
		persisted.Key,
		persisted.Namespace,
		source,
		persisted.Sharing,
		persisted.Owner,
	)
	if resultID == 0 {
		return cache, nil
	}
	links, err := loadPersistedSnapshotLinksByResultID(ctx, dag, resultID, "cache volume")
	if err != nil {
		return nil, err
	}

	type snapshotLink struct {
		index int
		link  dagql.PersistedSnapshotRefLink
	}
	snapshotLinks := make([]snapshotLink, 0, len(links))
	for _, link := range links {
		index, ok := cacheVolumeSnapshotRoleIndex(link.Role)
		if !ok {
			continue
		}
		snapshotLinks = append(snapshotLinks, snapshotLink{index: index, link: link})
	}
	sort.Slice(snapshotLinks, func(i, j int) bool {
		return snapshotLinks[i].index < snapshotLinks[j].index
	})

	for _, snapshotLink := range snapshotLinks {
		query, err := persistedDecodeQuery(dag)
		if err != nil {
			return nil, err
		}
		ref, err := query.SnapshotManager().GetMutableBySnapshotID(ctx, snapshotLink.link.RefKey, bkcache.NoUpdateLastUsed)
		if err != nil {
			return nil, fmt.Errorf("reopen persisted cache volume snapshot %q: %w", snapshotLink.link.RefKey, err)
		}
		cache.snapshots = append(cache.snapshots, &cacheVolumeSnapshot{ref: ref})
	}
	cache.selector = persisted.Selector
	if cache.selector == "" {
		cache.selector = "/"
	}
	return cache, nil
}

func (cache *CacheVolume) CacheUsageMayChange() bool {
	return true
}

func (cache *CacheVolume) invalidateSnapshotSize(ctx context.Context) error {
	cache.mu.Lock()
	snapshots := append([]*cacheVolumeSnapshot(nil), cache.snapshots...)
	cache.mu.Unlock()

	var rerr error
	for _, snapshot := range snapshots {
		if snapshot == nil || snapshot.ref == nil {
			continue
		}
		rerr = errors.Join(rerr, snapshot.ref.InvalidateSize(ctx))
	}
	return rerr
}

func (cache *CacheVolume) Sync(ctx context.Context) error {
	return cache.InitializeSnapshot(ctx)
}

func (cache *CacheVolume) InitializeSnapshot(ctx context.Context) error {
	cache.mu.Lock()
	defer cache.mu.Unlock()

	if len(cache.snapshots) > 0 {
		return nil
	}

	_, err := cache.createSnapshotLocked(ctx)
	return err
}

func (cache *CacheVolume) AcquireMount(ctx context.Context) (*CacheVolumeMount, error) {
	cache.mu.Lock()
	defer cache.mu.Unlock()

	switch cache.Sharing {
	case CacheSharingModePrivate:
		for _, snapshot := range cache.snapshots {
			if snapshot == nil || snapshot.ref == nil || snapshot.active {
				continue
			}
			snapshot.active = true
			return cache.mountForSnapshotLocked(snapshot), nil
		}
		snapshot, err := cache.createSnapshotLocked(ctx)
		if err != nil {
			return nil, err
		}
		snapshot.active = true
		return cache.mountForSnapshotLocked(snapshot), nil
	default:
		if len(cache.snapshots) == 0 {
			if _, err := cache.createSnapshotLocked(ctx); err != nil {
				return nil, err
			}
		}
		return cache.mountForSnapshotLocked(cache.snapshots[0]), nil
	}
}

func (cache *CacheVolume) mountForSnapshotLocked(snapshot *cacheVolumeSnapshot) *CacheVolumeMount {
	selector := cache.selector
	if selector == "" {
		selector = "/"
	}
	mount := &CacheVolumeMount{
		Ref:      snapshot.ref,
		Selector: selector,
	}
	if cache.Sharing == CacheSharingModePrivate {
		mount.release = func(context.Context) error {
			cache.mu.Lock()
			defer cache.mu.Unlock()
			snapshot.active = false
			return nil
		}
	}
	return mount
}

func (cache *CacheVolume) createSnapshotLocked(ctx context.Context) (*cacheVolumeSnapshot, error) {
	if cache == nil {
		return nil, fmt.Errorf("initialize cache volume snapshot: nil cache volume")
	}

	query, err := CurrentQuery(ctx)
	if err != nil {
		return nil, err
	}

	var source dagql.ObjectResult[*Directory]
	if cache.Source.Valid {
		srv, err := CurrentDagqlServer(ctx)
		if err != nil {
			return nil, err
		}
		source, err = cache.Source.Value.Load(ctx, srv)
		if err != nil {
			return nil, fmt.Errorf("failed to load cache volume source: %w", err)
		}
	}

	if cache.Owner != "" {
		if source.Self() == nil {
			srv, err := CurrentDagqlServer(ctx)
			if err != nil {
				return nil, err
			}
			if err := srv.Select(ctx, srv.Root(), &source, dagql.Selector{Field: "directory"}); err != nil {
				return nil, fmt.Errorf("failed to create scratch source directory for cache owner: %w", err)
			}
		}

		srv, err := CurrentDagqlServer(ctx)
		if err != nil {
			return nil, err
		}
		chowned := dagql.ObjectResult[*Directory]{}
		if err := srv.Select(ctx, source, &chowned, dagql.Selector{
			Field: "chown",
			Args: []dagql.NamedInput{
				{Name: "path", Value: dagql.String(".")},
				{Name: "owner", Value: dagql.String(cache.Owner)},
			},
		}); err != nil {
			return nil, fmt.Errorf("failed to chown cache source directory: %w", err)
		}
		source = chowned
	}

	sourceSelector := "/"
	var sourceRef bkcache.ImmutableRef
	if source.Self() != nil {
		dagCache, err := dagql.EngineCache(ctx)
		if err != nil {
			return nil, err
		}
		if err := dagCache.Evaluate(ctx, source); err != nil {
			return nil, fmt.Errorf("evaluate cache source directory: %w", err)
		}
		sourceSelector, err = source.Self().Dir.GetOrEval(ctx, source.Result)
		if err != nil {
			return nil, fmt.Errorf("failed to get cache source selector: %w", err)
		}
		if sourceSelector == "" {
			sourceSelector = "/"
		}
		sourceRef, err = source.Self().Snapshot.GetOrEval(ctx, source.Result)
		if err != nil {
			return nil, fmt.Errorf("failed to get cache source snapshot: %w", err)
		}
	}

	newRef, err := query.SnapshotManager().New(
		ctx,
		sourceRef,
		nil,
		bkcache.WithRecordType(bkclient.UsageRecordTypeCacheMount),
		bkcache.WithDescription(fmt.Sprintf("cache volume %q", cache.Key)),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize cache volume snapshot: %w", err)
	}

	if sourceSelector == "" {
		sourceSelector = "/"
	}
	cache.selector = sourceSelector
	snapshot := &cacheVolumeSnapshot{ref: newRef}
	cache.snapshots = append(cache.snapshots, snapshot)
	return snapshot, nil
}

type CacheSharingMode string

var CacheSharingModes = dagql.NewEnum[CacheSharingMode]()

var (
	CacheSharingModeShared = CacheSharingModes.Register("SHARED",
		"Shares the cache volume amongst many build pipelines")
	CacheSharingModePrivate = CacheSharingModes.Register("PRIVATE",
		"Keeps a cache volume for a single build pipeline")
	CacheSharingModeLocked = CacheSharingModes.Register("LOCKED",
		"Shares the cache volume amongst many build pipelines, but will serialize the writes")
)

func (mode CacheSharingMode) Type() *ast.Type {
	return &ast.Type{
		NamedType: "CacheSharingMode",
		NonNull:   true,
	}
}

func (mode CacheSharingMode) TypeDescription() string {
	return "Sharing mode of the cache volume."
}

func (mode CacheSharingMode) Decoder() dagql.InputDecoder {
	return CacheSharingModes
}

func (mode CacheSharingMode) ToLiteral() call.Literal {
	return CacheSharingModes.Literal(mode)
}

// CacheSharingMode marshals to its lowercased value.
//
// NB: as far as I can recall this is purely for ~*aesthetic*~. GraphQL consts
// are so shouty!
func (mode CacheSharingMode) MarshalJSON() ([]byte, error) {
	return json.Marshal(strings.ToLower(string(mode)))
}

// CacheSharingMode marshals to its lowercased value.
//
// NB: as far as I can recall this is purely for ~*aesthetic*~. GraphQL consts
// are so shouty!
func (mode *CacheSharingMode) UnmarshalJSON(payload []byte) error {
	var str string
	if err := json.Unmarshal(payload, &str); err != nil {
		return err
	}

	*mode = CacheSharingMode(strings.ToUpper(str))

	return nil
}
