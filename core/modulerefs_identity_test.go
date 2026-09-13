package core

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/dagger/dagger/core/workspace"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

const vanityResolutionOperation = "vanity-url-resolution"

type vanityIdentityFixture struct {
	lock     *workspace.Lock
	cache    *dagql.Cache
	status   atomic.Int32
	location atomic.Value
	requests atomic.Int32
}

func newVanityIdentityFixture(t *testing.T) *vanityIdentityFixture {
	t.Helper()
	f := &vanityIdentityFixture{lock: workspace.NewLock()}
	f.status.Store(http.StatusOK)
	f.location.Store("")
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.requests.Add(1)
		w.Header().Set("Location", f.location.Load().(string))
		w.WriteHeader(int(f.status.Load()))
	}))
	t.Cleanup(srv.Close)
	oldClient := daggerGetClient
	daggerGetClient = srv.Client()
	daggerGetClient.Transport.(*http.Transport).DialContext = func(ctx context.Context, network, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, network, srv.Listener.Addr().String())
	}
	daggerGetClient.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	t.Cleanup(func() { daggerGetClient = oldClient })
	var err error
	f.cache, err = dagql.NewCache(t.Context(), "", nil, nil)
	require.NoError(t, err)
	return f
}

func (f *vanityIdentityFixture) ctx(t *testing.T, session string, writable bool) context.Context {
	ctx := ContextWithQuery(t.Context(), &Query{Server: &mockServer{workspaceLock: f.lock, lockWritable: writable}})
	ctx = engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{SessionID: session})
	return dagql.ContextWithCache(ctx, f.cache)
}

func TestResolveDaggerGetRedirectLocksSuccessfulIdentity(t *testing.T) {
	for _, input := range []string{
		"https://127.0.0.1/repo",
		"127.0.0.1/repo",
		"127.0.0.1/repo@v1.2.3",
		"https://127.0.0.1/repo@main",
		"https://127.0.0.1/repo#main:module/nested",
		"https://127.0.0.1/repo#0123456789012345678901234567890123456789:module",
	} {
		t.Run(input, func(t *testing.T) {
			f := newVanityIdentityFixture(t)
			for _, session := range []string{"first", "second"} {
				got, err := ResolveDaggerGetRedirect(f.ctx(t, session, true), input)
				require.NoError(t, err)
				require.Equal(t, input, got, "identity must preserve transport, selector kind and subpath")
				// Exercise serialized state, not just the same in-memory lock object.
				data, err := f.lock.Marshal()
				require.NoError(t, err)
				f.lock, err = workspace.ParseLock(data)
				require.NoError(t, err)
			}
			require.EqualValues(t, 1, f.requests.Load(), "fresh session must reuse the recorded identity")
			entries := f.lock.Entries()
			require.Len(t, entries, 1)
			require.Equal(t, vanityResolutionOperation, entries[0].Operation, "legacy readers cannot safely interpret self-values")
			require.Equal(t, "https://127.0.0.1/repo", entries[0].Value)
		})
	}
}

func TestResolveDaggerGetRedirectIdentityReadOnly(t *testing.T) {
	f := newVanityIdentityFixture(t)
	const input = "https://127.0.0.1/repo#main:module"
	for _, session := range []string{"first", "second"} {
		got, err := ResolveDaggerGetRedirect(f.ctx(t, session, false), input)
		require.NoError(t, err)
		require.Equal(t, input, got)
	}
	require.Empty(t, f.lock.Entries())
	require.EqualValues(t, 2, f.requests.Load())
}

func TestResolveDaggerGetRedirectIdentityRejectsFallbacks(t *testing.T) {
	for _, tc := range []struct {
		name     string
		status   int
		location string
	}{
		{name: "unauthorized", status: 401},
		{name: "forbidden", status: 403},
		{name: "not found", status: 404},
		{name: "rate limited", status: 429},
		{name: "server failure", status: 500},
		{name: "missing location", status: 302},
		{name: "login redirect", status: 302, location: "https://127.0.0.1/sign_in"},
		{name: "invalid redirect", status: 302, location: "https://%invalid"},
		{name: "insecure redirect", status: 302, location: "http://example.com/repo?dagger-get=1"},
		{name: "canonicalization", status: 301, location: "https://127.0.0.1/repo.git?dagger-get=1"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newVanityIdentityFixture(t)
			f.status.Store(int32(tc.status))
			f.location.Store(tc.location)
			for _, session := range []string{"first", "second"} {
				got, err := ResolveDaggerGetRedirect(f.ctx(t, session, true), "https://127.0.0.1/repo")
				require.NoError(t, err)
				require.Equal(t, "https://127.0.0.1/repo", got)
			}
			require.Empty(t, f.lock.Entries(), "fallback must not become a durable identity result")
			require.EqualValues(t, 2, f.requests.Load())
		})
	}
}

type vanityIdentityTransport func(*http.Request) (*http.Response, error)

func (fn vanityIdentityTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestResolveDaggerGetRedirectIdentityCancellation(t *testing.T) {
	f := newVanityIdentityFixture(t)
	entered := make(chan struct{})
	transportDone := make(chan struct{})
	var started, finished sync.Once
	daggerGetClient.Transport = vanityIdentityTransport(func(req *http.Request) (*http.Response, error) {
		started.Do(func() { close(entered) })
		<-req.Context().Done()
		finished.Do(func() { close(transportDone) })
		return nil, req.Context().Err()
	})
	ctx, cancel := context.WithCancel(f.ctx(t, "cancelled", true))
	defer cancel()
	type result struct {
		ref string
		err error
	}
	done := make(chan result, 1)
	go func() {
		ref, err := ResolveDaggerGetRedirect(ctx, "https://127.0.0.1/repo")
		done <- result{ref, err}
	}()
	// The cache callback can outlive its cancelled waiter. Join the controlled
	// transport before restoring the global test client; don't sleep for it.
	select {
	case <-entered:
	case <-time.After(5 * time.Second):
		t.Fatal("probe did not enter the controlled transport")
	}
	cancel()
	select {
	case got := <-done:
		require.NoError(t, got.err)
		require.Equal(t, "https://127.0.0.1/repo", got.ref)
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled resolver did not return")
	}
	select {
	case <-transportDone:
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled transport did not return")
	}
	require.Empty(t, f.lock.Entries())
}

func TestResolveDaggerGetRedirectIdentityDoesNotPersistSensitiveURLs(t *testing.T) {
	for _, input := range []string{
		"https://synthetic-user:synthetic-password@127.0.0.1/repo@main",
		"https://127.0.0.1/repo@main?token=synthetic-token",
	} {
		t.Run(input, func(t *testing.T) {
			f := newVanityIdentityFixture(t)
			for _, session := range []string{"first", "second"} {
				got, err := ResolveDaggerGetRedirect(f.ctx(t, session, true), input)
				require.NoError(t, err)
				require.Equal(t, input, got)
			}
			require.Empty(t, f.lock.Entries())
			require.EqualValues(t, 2, f.requests.Load())
		})
	}
}

func TestResolveDaggerGetRedirectIdentitySharesSourceOnly(t *testing.T) {
	f := newVanityIdentityFixture(t)
	for i, input := range []string{
		"127.0.0.1/repo@v1.2.3",
		"https://127.0.0.1/repo#main:module/nested",
		"https://127.0.0.1/repo@other",
	} {
		// Later reads are read-only, from independent sessions and selectors.
		got, err := ResolveDaggerGetRedirect(f.ctx(t, input, i == 0), input)
		require.NoError(t, err)
		require.Equal(t, input, got)
	}
	require.EqualValues(t, 1, f.requests.Load())
}

func TestVanityURLResolutionRefresh(t *testing.T) {
	f := newVanityIdentityFixture(t)
	const source = "https://127.0.0.1/repo"
	require.NoError(t, f.lock.SetLookup("", vanityResolutionOperation, []any{source}, source))
	require.NoError(t, UpdateWorkspaceLock(t.Context(), nil, f.lock))
	require.EqualValues(t, 1, f.requests.Load(), "explicit update must actually refresh identity entries")
	f.location.Store("https://github.com/dagger/dagger@v1.2.3?dagger-get=1")
	f.status.Store(http.StatusTemporaryRedirect)
	require.NoError(t, UpdateWorkspaceLock(t.Context(), nil, f.lock))
	value, ok := f.lock.GetLookup("", vanityResolutionOperation, []any{source})
	require.True(t, ok)
	require.Equal(t, "https://github.com/dagger/dagger@v1.2.3", value)
	got, err := ResolveDaggerGetRedirect(f.ctx(t, "replay", true), source+"@other")
	require.NoError(t, err)
	require.Equal(t, "https://github.com/dagger/dagger@other", got)
	require.EqualValues(t, 2, f.requests.Load())
	// A disappeared redirect must not silently undo a previously pinned mapping.
	f.status.Store(http.StatusOK)
	require.Error(t, UpdateWorkspaceLock(t.Context(), nil, f.lock))
	value, ok = f.lock.GetLookup("", vanityResolutionOperation, []any{source})
	require.True(t, ok)
	require.Equal(t, "https://github.com/dagger/dagger@v1.2.3", value)
}

func TestVanityURLResolutionPreservesIdentityOnRefreshFailure(t *testing.T) {
	f := newVanityIdentityFixture(t)
	const source = "https://127.0.0.1/repo"
	f.status.Store(http.StatusInternalServerError)
	require.NoError(t, f.lock.SetLookup("", vanityResolutionOperation, []any{source}, source))
	require.Error(t, UpdateWorkspaceLock(t.Context(), nil, f.lock))
	value, ok := f.lock.GetLookup("", vanityResolutionOperation, []any{source})
	require.True(t, ok)
	require.Equal(t, source, value)
}

func TestVanityURLResolutionLegacyPositivePrecedence(t *testing.T) {
	for _, newValue := range []string{"https://127.0.0.1/repo", "https://example.com/new"} {
		t.Run(strings.TrimPrefix(newValue, "https://"), func(t *testing.T) {
			lock := workspace.NewLock()
			const source = "https://127.0.0.1/repo"
			require.NoError(t, lock.SetLookup("", vanityResolutionOperation, []any{source}, newValue))
			// An older engine ignores the new operation and may write this entry.
			require.NoError(t, lock.SetLookup("", workspace.LockOperationVanityURL, []any{source}, "https://example.com/legacy"))
			got, err := ResolveDaggerGetRedirect(ContextWithVanityURLLookupLock(t.Context(), lock), source+"@main")
			require.NoError(t, err)
			require.Equal(t, "https://example.com/legacy@main", got)
		})
	}
}

func TestVanityURLResolutionLegacyRefresh(t *testing.T) {
	f := newVanityIdentityFixture(t)
	const source = "https://127.0.0.1/repo"
	const destination = "https://github.com/dagger/dagger@v1.2.3"
	f.status.Store(http.StatusTemporaryRedirect)
	f.location.Store(destination + "?dagger-get=1")
	require.NoError(t, f.lock.SetLookup("", vanityResolutionOperation, []any{source}, source))
	require.NoError(t, f.lock.SetLookup("", workspace.LockOperationVanityURL, []any{source}, "https://example.com/old"))
	require.NoError(t, UpdateWorkspaceLock(t.Context(), nil, f.lock))
	require.EqualValues(t, 1, f.requests.Load(), "refresh the authoritative mapping once")
	for _, operation := range []string{workspace.LockOperationVanityURL, vanityResolutionOperation} {
		value, ok := f.lock.GetLookup("", operation, []any{source})
		require.True(t, ok)
		require.Equal(t, destination, value)
	}
	f.status.Store(http.StatusOK)
	require.Error(t, UpdateWorkspaceLock(t.Context(), nil, f.lock), "legacy positive failure semantics still apply")
	for _, operation := range []string{workspace.LockOperationVanityURL, vanityResolutionOperation} {
		value, ok := f.lock.GetLookup("", operation, []any{source})
		require.True(t, ok)
		require.Equal(t, destination, value)
	}
}
