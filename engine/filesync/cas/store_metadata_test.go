package cas

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	bkcache "github.com/dagger/dagger/internal/buildkit/cache"
	"github.com/dagger/dagger/internal/buildkit/cache/metadata"
	"github.com/dagger/dagger/internal/buildkit/client"
	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestHeadStoreSaveLoad(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	md := store.newRef("ref-1")
	headStore := ScopeHeadStore{Store: store}

	scope := ScopeKey(digest.FromString("scope").String())
	head := ScopeHead{
		Scope:      scope,
		RootDigest: digest.FromString("root-1"),
		Generation: 1,
		ChainDepth: 1,
	}

	err := headStore.Save(t.Context(), md, head, 0)
	assert.NilError(t, err)

	loaded, found, err := headStore.Load(t.Context(), scope)
	assert.NilError(t, err)
	assert.Assert(t, found)
	assert.Equal(t, loaded.Scope, scope)
	assert.Equal(t, loaded.RootDigest, head.RootDigest)
	assert.Equal(t, loaded.Generation, uint64(1))
	assert.Equal(t, loaded.MaterialRefID, "ref-1")
}

func TestHeadStoreGenerationCheck(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	headStore := ScopeHeadStore{Store: store}
	scope := ScopeKey(digest.FromString("scope").String())

	firstRef := store.newRef("ref-a")
	first := ScopeHead{
		Scope:      scope,
		RootDigest: digest.FromString("root-a"),
		Generation: 1,
	}
	assert.NilError(t, headStore.Save(t.Context(), firstRef, first, 0))

	secondRef := store.newRef("ref-b")
	invalid := ScopeHead{
		Scope:      scope,
		RootDigest: digest.FromString("root-b"),
		Generation: 3, // must be current+1
	}
	err := headStore.Save(t.Context(), secondRef, invalid, 1)
	assert.Assert(t, is.ErrorContains(err, "must increment by 1"))
}

func TestHeadStoreCorruptPayload(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	scope := ScopeKey(digest.FromString("scope").String())

	md := store.newRef("bad-ref")
	assert.NilError(t, md.SetString(keyScopeHeadScope, scope.String(), scopeHeadScopeIndex+scope.String()))
	assert.NilError(t, md.SetExternal(keyScopeHeadPayload, []byte("{invalid-json")))

	headStore := ScopeHeadStore{Store: store}
	_, _, err := headStore.Load(t.Context(), scope)
	assert.Assert(t, is.ErrorContains(err, "unmarshal scope head payload"))
}

func TestManifestStoreSaveLoad(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	md := store.newRef("manifest-ref")
	manifestStore := ManifestStore{Store: store}

	manifest := Manifest{
		Scope: ScopeKey(digest.FromString("scope").String()),
		Entries: map[string]Entry{
			"dir/file.txt": {
				Path:       "dir/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("content"),
			},
		},
	}

	assert.NilError(t, manifestStore.Save(md, manifest))
	root, err := RootDigest(manifest)
	assert.NilError(t, err)

	loaded, found, err := manifestStore.Load(t.Context(), root)
	assert.NilError(t, err)
	assert.Assert(t, found)
	assert.Equal(t, loaded.RootDigest, root)
	assert.Assert(t, is.Len(loaded.Entries, 1))
}

func TestManifestStoreCorruptPayload(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	manifestStore := ManifestStore{Store: store}

	root := digest.FromString("root")
	md := store.newRef("manifest-bad")
	assert.NilError(t, md.SetString(keyManifestRootDigest, root.String(), manifestRootIndex+root.String()))
	assert.NilError(t, md.SetExternal(keyManifestPayload, []byte("{not-json")))

	_, _, err := manifestStore.Load(t.Context(), root)
	assert.Assert(t, is.ErrorContains(err, "parse manifest"))
}

type fakeMetadataStore struct {
	mu    sync.Mutex
	refs  map[string]*fakeRefMetadata
	index map[string]map[string]struct{}
}

func newFakeMetadataStore() *fakeMetadataStore {
	return &fakeMetadataStore{
		refs:  map[string]*fakeRefMetadata{},
		index: map[string]map[string]struct{}{},
	}
}

func (s *fakeMetadataStore) newRef(id string) *fakeRefMetadata {
	s.mu.Lock()
	defer s.mu.Unlock()

	ref := &fakeRefMetadata{
		id:          id,
		store:       s,
		strings:     map[string]string{},
		externals:   map[string][]byte{},
		indexByKey:  map[string]string{},
		cachePolicy: "default",
	}
	s.refs[id] = ref
	return ref
}

func (s *fakeMetadataStore) Search(_ context.Context, idx string, prefixOnly bool) ([]bkcache.RefMetadata, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	ids := map[string]struct{}{}
	if prefixOnly {
		for key, values := range s.index {
			if strings.HasPrefix(key, idx) {
				for id := range values {
					ids[id] = struct{}{}
				}
			}
		}
	} else {
		for id := range s.index[idx] {
			ids[id] = struct{}{}
		}
	}

	sortedIDs := make([]string, 0, len(ids))
	for id := range ids {
		sortedIDs = append(sortedIDs, id)
	}
	sort.Strings(sortedIDs)

	results := make([]bkcache.RefMetadata, 0, len(sortedIDs))
	for _, id := range sortedIDs {
		if ref, ok := s.refs[id]; ok {
			results = append(results, ref)
		}
	}
	return results, nil
}

func (s *fakeMetadataStore) addIndex(idx, id string) {
	if idx == "" {
		return
	}
	if _, ok := s.index[idx]; !ok {
		s.index[idx] = map[string]struct{}{}
	}
	s.index[idx][id] = struct{}{}
}

func (s *fakeMetadataStore) removeIndex(idx, id string) {
	if idx == "" {
		return
	}
	values, ok := s.index[idx]
	if !ok {
		return
	}
	delete(values, id)
	if len(values) == 0 {
		delete(s.index, idx)
	}
}

type fakeRefMetadata struct {
	id          string
	store       *fakeMetadataStore
	strings     map[string]string
	externals   map[string][]byte
	indexByKey  map[string]string
	createdAt   time.Time
	layerType   string
	recordType  client.UsageRecordType
	cachePolicy string
}

func (m *fakeRefMetadata) ID() string {
	return m.id
}

func (m *fakeRefMetadata) GetDescription() string {
	return m.strings["description"]
}

func (m *fakeRefMetadata) SetDescription(value string) error {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()
	m.strings["description"] = value
	return nil
}

func (m *fakeRefMetadata) GetCreatedAt() time.Time {
	return m.createdAt
}

func (m *fakeRefMetadata) SetCreatedAt(value time.Time) error {
	m.createdAt = value
	return nil
}

func (m *fakeRefMetadata) HasCachePolicyDefault() bool {
	return m.cachePolicy == "default"
}

func (m *fakeRefMetadata) SetCachePolicyDefault() error {
	m.cachePolicy = "default"
	return nil
}

func (m *fakeRefMetadata) HasCachePolicyRetain() bool {
	return m.cachePolicy == "retain"
}

func (m *fakeRefMetadata) SetCachePolicyRetain() error {
	m.cachePolicy = "retain"
	return nil
}

func (m *fakeRefMetadata) GetLayerType() string {
	return m.layerType
}

func (m *fakeRefMetadata) SetLayerType(value string) error {
	m.layerType = value
	return nil
}

func (m *fakeRefMetadata) GetRecordType() client.UsageRecordType {
	return m.recordType
}

func (m *fakeRefMetadata) SetRecordType(value client.UsageRecordType) error {
	m.recordType = value
	return nil
}

func (m *fakeRefMetadata) GetEqualMutable() (bkcache.RefMetadata, bool) {
	return nil, false
}

func (m *fakeRefMetadata) GetString(key string) string {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()
	return m.strings[key]
}

func (m *fakeRefMetadata) Get(string) *metadata.Value {
	return nil
}

func (m *fakeRefMetadata) SetString(key, value, index string) error {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()

	if oldIndex := m.indexByKey[key]; oldIndex != "" {
		m.store.removeIndex(oldIndex, m.id)
	}
	m.strings[key] = value
	m.indexByKey[key] = index
	m.store.addIndex(index, m.id)
	return nil
}

func (m *fakeRefMetadata) GetExternal(key string) ([]byte, error) {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()

	value, ok := m.externals[key]
	if !ok {
		return nil, nil
	}
	return append([]byte(nil), value...), nil
}

func (m *fakeRefMetadata) SetExternal(key string, value []byte) error {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()
	m.externals[key] = append([]byte(nil), value...)
	return nil
}

func (m *fakeRefMetadata) ClearValueAndIndex(key, index string) error {
	m.store.mu.Lock()
	defer m.store.mu.Unlock()

	delete(m.strings, key)
	delete(m.indexByKey, key)
	m.store.removeIndex(index, m.id)
	return nil
}

var _ bkcache.MetadataStore = (*fakeMetadataStore)(nil)
var _ bkcache.RefMetadata = (*fakeRefMetadata)(nil)

func (m *fakeRefMetadata) String() string {
	return fmt.Sprintf("fakeRefMetadata(%s)", m.id)
}
