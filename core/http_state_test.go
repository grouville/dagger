package core

import (
	"context"
	"fmt"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/containerd/containerd/v2/core/mount"
	"github.com/containerd/containerd/v2/core/snapshots"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/internal/buildkit/executor/oci"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
)

func TestHTTPStatePinnedReuse(t *testing.T) {
	origin, state, query, _ := newHTTPStateTest(t)
	checksum := httpStateTestChecksum("original")
	first := resolveHTTPStateTest(t, state, query, checksum, "first", 0o640)
	assertHTTPStateTestFile(t, first, "original", "first", 0o640)

	// A pin addresses the previously verified bytes, not the current URL
	// response. Neither changed validators/body nor an unavailable origin should
	// require a request while the matching snapshot is retained.
	origin.set("replacement", `"replacement"`, "Thu, 02 Jan 2020 00:00:00 GMT")
	second := resolveHTTPStateTest(t, state, query, checksum, "second", 0o751)
	assertHTTPStateTestFile(t, second, "original", "second", 0o751)
	require.Equal(t, first.LastModified, second.LastModified)
	require.Equal(t, 1, origin.requestCount())

	origin.server.Close()
	third := resolveHTTPStateTest(t, state, query, checksum, "third", 0o600)
	assertHTTPStateTestFile(t, third, "original", "third", 0o600)
	require.Equal(t, 1, origin.requestCount())
	// Creating each outward file must not rename or chmod earlier results.
	assertHTTPStateTestFile(t, first, "original", "first", 0o640)
}

func TestHTTPStateUnpinnedRevalidation(t *testing.T) {
	for _, validator := range []string{"etag", "last-modified"} {
		t.Run(validator, func(t *testing.T) {
			origin, state, query, _ := newHTTPStateTest(t)
			if validator == "last-modified" {
				origin.set("original", "", "Wed, 01 Jan 2020 00:00:00 GMT")
			}
			// Warm through a pin, then remove the pin: that must not accidentally
			// make the otherwise mutable URL immutable.
			first := resolveHTTPStateTest(t, state, query, httpStateTestChecksum("original"), "file", 0o600)
			second := resolveHTTPStateTest(t, state, query, dagql.Optional[dagql.String]{}, "file", 0o600)
			assertHTTPStateTestFile(t, second, "original", "file", 0o600)
			require.Equal(t, first.LastModified, second.LastModified)
			require.Equal(t, 2, origin.requestCount())
			if validator == "etag" {
				require.Equal(t, `"original"`, origin.requestHeader(1, "If-None-Match"))
			} else {
				require.Equal(t, first.LastModified, origin.requestHeader(1, "If-Modified-Since"))
			}

			origin.set("replacement", `"replacement"`, "Thu, 02 Jan 2020 00:00:00 GMT")
			// An explicitly supplied empty checksum is also unpinned.
			third := resolveHTTPStateTest(t, state, query, dagql.Opt(dagql.String("")), "file", 0o600)
			assertHTTPStateTestFile(t, third, "replacement", "file", 0o600)
			require.Equal(t, 3, origin.requestCount())
			assertHTTPStateTestFile(t, first, "original", "file", 0o600)
		})
	}
}

func TestHTTPStateChecksumChanges(t *testing.T) {
	origin, state, query, _ := newHTTPStateTest(t)
	original := httpStateTestChecksum("original")
	resolveHTTPStateTest(t, state, query, original, "file", 0o600)
	ctx := httpStateTestContext(t, query, "changed-checksum")

	_, err := state.Resolve(ctx, query, dagql.Opt(dagql.String("not-a-digest")), 0o600, "file")
	require.ErrorContains(t, err, "invalid checksum")
	require.Equal(t, 1, origin.requestCount(), "invalid checksums fail before contacting the origin")

	// A changed expected digest must not reuse the old snapshot. Even a 304
	// response only validates the retained bytes, which do not match this pin.
	replacement := httpStateTestChecksum("replacement")
	_, err = state.Resolve(ctx, query, replacement, 0o600, "file")
	require.ErrorContains(t, err, "http checksum mismatch")
	require.Equal(t, 2, origin.requestCount())
	require.Equal(t, digest.FromString("original"), state.ContentDigest)

	// A 200 mismatch must also leave the last verified snapshot intact.
	origin.set("wrong-body", `"wrong-body"`, "Thu, 02 Jan 2020 00:00:00 GMT")
	_, err = state.Resolve(ctx, query, replacement, 0o600, "file")
	require.ErrorContains(t, err, "http checksum mismatch")
	require.Equal(t, 3, origin.requestCount())
	require.Equal(t, digest.FromString("original"), state.ContentDigest)
	stillOriginal := resolveHTTPStateTest(t, state, query, original, "file", 0o600)
	assertHTTPStateTestFile(t, stillOriginal, "original", "file", 0o600)
	require.Equal(t, 3, origin.requestCount())

	origin.set("replacement", `"replacement"`, "Fri, 03 Jan 2020 00:00:00 GMT")
	updated := resolveHTTPStateTest(t, state, query, replacement, "file", 0o600)
	assertHTTPStateTestFile(t, updated, "replacement", "file", 0o600)
	require.Equal(t, 4, origin.requestCount())
	resolveHTTPStateTest(t, state, query, replacement, "file", 0o600)
	require.Equal(t, 4, origin.requestCount())
}

func TestHTTPStatePinnedSnapshotReopen(t *testing.T) {
	origin, state, query, manager := newHTTPStateTest(t)
	checksum := httpStateTestChecksum("original")
	resolveHTTPStateTest(t, state, query, checksum, "file", 0o600)

	encoded, err := state.EncodePersistedObject(t.Context(), nil)
	require.NoError(t, err)
	require.Len(t, encoded.SnapshotLinks, 1)
	decoded, err := new(HTTPState).DecodePersistedObject(t.Context(), nil, 0, nil, encoded.JSON)
	require.NoError(t, err)
	reopened := decoded.(*HTTPState)
	// The real cache importer supplies this snapshot ownership link separately
	// from the self payload. This fixture tests reopening, not dagql persistence.
	reopened.snapshotID = encoded.SnapshotLinks[0].RefKey
	t.Cleanup(func() { require.NoError(t, reopened.OnRelease(context.Background())) })
	require.Nil(t, reopened.snapshot)
	origin.server.Close()

	result := resolveHTTPStateTest(t, reopened, query, checksum, "renamed", 0o755)
	assertHTTPStateTestFile(t, result, "original", "renamed", 0o755)
	require.Equal(t, 1, origin.requestCount())
	require.Equal(t, 1, manager.reopenCount())
	require.Equal(t, encoded.SnapshotLinks, reopened.PersistedSnapshotRefLinks())
}

func TestHTTPStatePinRequiresSnapshot(t *testing.T) {
	origin, state, query, _ := newHTTPStateTest(t)
	state.ContentDigest = digest.FromString("original")
	state.snapshotID = "missing-snapshot"
	// A persisted digest alone is not enough: reopening its retained bytes must
	// succeed. Preserve the existing fail-closed behavior for a broken link.
	_, err := state.Resolve(httpStateTestContext(t, query, "missing"), query, httpStateTestChecksum("original"), 0o600, "file")
	require.ErrorContains(t, err, "reopen http state snapshot")
	require.Equal(t, 0, origin.requestCount())
}

func TestHTTPStatePinnedConcurrentResolve(t *testing.T) {
	origin, state, query, _ := newHTTPStateTest(t)
	const clients = 8
	results := make([]*HTTPFetchResult, clients)
	errs := make([]error, clients)
	start := make(chan struct{})
	var wg sync.WaitGroup
	for i := range clients {
		wg.Go(func() {
			<-start
			results[i], errs[i] = state.Resolve(
				httpStateTestContext(t, query, fmt.Sprintf("client-%d", i)),
				query, httpStateTestChecksum("original"), 0o640, fmt.Sprintf("file-%d", i),
			)
		})
	}
	close(start)
	wg.Wait()
	for i := range clients {
		require.NoError(t, errs[i])
		t.Cleanup(func() { require.NoError(t, results[i].File.OnRelease(context.Background())) })
		assertHTTPStateTestFile(t, results[i], "original", fmt.Sprintf("file-%d", i), 0o640)
	}
	require.Equal(t, 1, origin.requestCount(), "the state mutex should serialize first fetch and pinned reuse")
}

func TestHTTPStatePinnedCancellation(t *testing.T) {
	origin, state, query, _ := newHTTPStateTest(t)
	checksum := httpStateTestChecksum("original")
	resolveHTTPStateTest(t, state, query, checksum, "file", 0o600)
	ctx, cancel := context.WithCancel(httpStateTestContext(t, query, "cancelled"))
	cancel()
	_, err := state.Resolve(ctx, query, checksum, 0o600, "file")
	require.ErrorIs(t, err, context.Canceled)
	require.Equal(t, 1, origin.requestCount())
}

func httpStateTestChecksum(content string) dagql.Optional[dagql.String] {
	return dagql.Opt(dagql.String(digest.FromString(content).String()))
}

func httpStateTestContext(t *testing.T, query *Query, session string) context.Context {
	return engine.ContextWithClientMetadata(ContextWithQuery(t.Context(), query), &engine.ClientMetadata{SessionID: session})
}

func resolveHTTPStateTest(t *testing.T, state *HTTPState, query *Query, checksum dagql.Optional[dagql.String], name string, permissions int) *HTTPFetchResult {
	t.Helper()
	result, err := state.Resolve(httpStateTestContext(t, query, name), query, checksum, permissions, name)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, result.File.OnRelease(context.Background())) })
	return result
}

func assertHTTPStateTestFile(t *testing.T, result *HTTPFetchResult, contents, name string, permissions fs.FileMode) {
	t.Helper()
	actualName, ok := result.File.File.Peek()
	require.True(t, ok)
	require.Equal(t, name, actualName)
	ref, ok := result.File.Snapshot.Peek()
	require.True(t, ok)
	path := filepath.Join(ref.(*httpStateTestRef).dir, name)
	actual, err := os.ReadFile(path)
	require.NoError(t, err)
	require.Equal(t, contents, string(actual))
	info, err := os.Stat(path)
	require.NoError(t, err)
	require.Equal(t, permissions, info.Mode().Perm())
	modified, err := http.ParseTime(result.LastModified)
	require.NoError(t, err)
	require.Equal(t, modified.Unix(), info.ModTime().Unix())
}

type httpStateTestOrigin struct {
	server               *httptest.Server
	mu                   sync.Mutex
	body, etag, modified string
	requests             []http.Header
}

func (o *httpStateTestOrigin) set(body, etag, modified string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.body, o.etag, o.modified = body, etag, modified
}

func (o *httpStateTestOrigin) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.requests = append(o.requests, r.Header.Clone())
	w.Header().Set("ETag", o.etag)
	w.Header().Set("Last-Modified", o.modified)
	if (o.etag != "" && r.Header.Get("If-None-Match") == o.etag) ||
		(o.etag == "" && r.Header.Get("If-Modified-Since") == o.modified) {
		w.WriteHeader(http.StatusNotModified)
		return
	}
	fmt.Fprint(w, o.body)
}

func (o *httpStateTestOrigin) requestCount() int {
	o.mu.Lock()
	defer o.mu.Unlock()
	return len(o.requests)
}

func (o *httpStateTestOrigin) requestHeader(index int, name string) string {
	o.mu.Lock()
	defer o.mu.Unlock()
	return o.requests[index].Get(name)
}

func newHTTPStateTest(t *testing.T) (*httpStateTestOrigin, *HTTPState, *Query, *httpStateTestSnapshotManager) {
	t.Helper()
	origin := &httpStateTestOrigin{body: "original", etag: `"original"`, modified: "Wed, 01 Jan 2020 00:00:00 GMT"}
	origin.server = httptest.NewServer(origin)
	t.Cleanup(origin.server.Close)
	manager := &httpStateTestSnapshotManager{root: t.TempDir(), snapshots: make(map[string]*httpStateTestRef)}
	query := &Query{Server: &httpStateTestQueryServer{cacheVolumeTestQueryServer: cacheVolumeTestQueryServer{
		mockServer: &mockServer{}, cacheManager: manager,
	}}}
	state := &HTTPState{URL: origin.server.URL + "/payload"}
	t.Cleanup(func() { require.NoError(t, state.OnRelease(context.Background())) })
	return origin, state, query, manager
}

type httpStateTestQueryServer struct{ cacheVolumeTestQueryServer }

func (*httpStateTestQueryServer) DNS() *oci.DNSConfig { return &oci.DNSConfig{} }

// These snapshot fixtures exercise real file writes, copies, renames, modes and
// timestamps without privileged mounts. New copies its parent's files, so a
// derived result cannot accidentally mutate its canonical immutable snapshot.
// They do not model containerd leases or dagql result retention/GC.
type httpStateTestSnapshotManager struct {
	cacheVolumeTestSnapshotManager
	root      string
	mu        sync.Mutex
	snapshots map[string]*httpStateTestRef
	reopens   int
}

func (m *httpStateTestSnapshotManager) New(_ context.Context, parent bkcache.ImmutableRef, _ ...bkcache.RefOption) (bkcache.MutableRef, error) {
	dir, err := os.MkdirTemp(m.root, "snapshot-")
	if err != nil {
		return nil, err
	}
	if parent != nil {
		src := parent.(*httpStateTestRef).dir
		entries, err := os.ReadDir(src)
		if err != nil {
			return nil, err
		}
		for _, entry := range entries {
			info, err := entry.Info()
			if err != nil {
				return nil, err
			}
			if !info.Mode().IsRegular() {
				return nil, fmt.Errorf("unsupported fixture file %s", entry.Name())
			}
			contents, err := os.ReadFile(filepath.Join(src, entry.Name()))
			if err != nil {
				return nil, err
			}
			dst := filepath.Join(dir, entry.Name())
			if err := os.WriteFile(dst, contents, info.Mode().Perm()); err != nil {
				return nil, err
			}
			if err := os.Chmod(dst, info.Mode().Perm()); err != nil {
				return nil, err
			}
			if err := os.Chtimes(dst, info.ModTime(), info.ModTime()); err != nil {
				return nil, err
			}
		}
	}
	ref := &httpStateTestRef{cacheVolumeTestImmutableRef: cacheVolumeTestImmutableRef{
		id: filepath.Base(dir), snapshotID: filepath.Base(dir),
	}, dir: dir}
	return &httpStateTestMutableRef{httpStateTestRef: ref, manager: m}, nil
}

func (m *httpStateTestSnapshotManager) GetBySnapshotID(_ context.Context, id string, _ ...bkcache.RefOption) (bkcache.ImmutableRef, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.reopens++
	ref, ok := m.snapshots[id]
	if !ok {
		return nil, fmt.Errorf("missing test snapshot %q", id)
	}
	return ref, nil
}

func (m *httpStateTestSnapshotManager) reopenCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.reopens
}

type httpStateTestRef struct {
	cacheVolumeTestImmutableRef
	dir string
}

func (r *httpStateTestRef) Mount(context.Context, bool) (bkcache.MountableRef, error) {
	return httpStateTestMount(r.dir), nil
}

type httpStateTestMount string

func (m httpStateTestMount) Mount() ([]mount.Mount, func() error, error) {
	return []mount.Mount{{Type: "bind", Source: string(m), Options: []string{"rw"}}}, func() error { return nil }, nil
}

type httpStateTestMutableRef struct {
	*httpStateTestRef
	manager *httpStateTestSnapshotManager
}

func (r *httpStateTestMutableRef) Commit(context.Context) (bkcache.ImmutableRef, error) {
	r.manager.mu.Lock()
	defer r.manager.mu.Unlock()
	r.manager.snapshots[r.SnapshotID()] = r.httpStateTestRef
	return r.httpStateTestRef, nil
}

func (r *httpStateTestMutableRef) CommitWithUsage(ctx context.Context, _ snapshots.Usage) (bkcache.ImmutableRef, error) {
	return r.Commit(ctx)
}

func (*httpStateTestMutableRef) InvalidateSize(context.Context) error { return nil }
