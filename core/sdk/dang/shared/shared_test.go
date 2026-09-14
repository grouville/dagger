package dangshared

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Khan/genqlient/graphql"
	"github.com/stretchr/testify/require"
)

// Well under net/http's 5s grace for StateNew connections during Shutdown.
const nestedTestTimeout = 3 * time.Second

// Reproduces the stray-connection case: request A holds the only connection,
// request B starts a dial, A finishes and B reuses A's connection, then B's
// dial completes and the new connection never carries a request. Without
// CloseIdleConnections before Shutdown, the invocation stalls ~5s here.
func TestServeNestedClientClosesUnusedConnection(t *testing.T) {
	firstEntered := make(chan struct{})
	releaseFirst := make(chan struct{})
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req graphql.Request
		require.NoError(t, json.NewDecoder(r.Body).Decode(&req))
		if req.OpName == "First" {
			close(firstEntered)
			<-releaseFirst
		}
		okResponse(w)
	})}
	var accepted atomic.Int32
	srv.ConnState = func(_ net.Conn, state http.ConnState) {
		if state == http.StateNew {
			accepted.Add(1)
		}
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	var dials atomic.Int32
	secondDialStarted := make(chan struct{})
	releaseSecondDial := make(chan struct{})
	dial := (&net.Dialer{}).DialContext
	transport.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
		if dials.Add(1) == 2 {
			close(secondDialStarted)
			<-releaseSecondDial
		}
		return dial(ctx, network, addr)
	}

	done := make(chan error, 1)
	go func() {
		_, err := serveNestedClient(t.Context(), srv, transport, func(ctx context.Context, client graphql.Client) ([]byte, error) {
			first := request(ctx, client, "First")
			waitFor(t, firstEntered, "first request in handler")
			second := request(ctx, client, "Second")
			waitFor(t, secondDialStarted, "second request dialing")
			close(releaseFirst)
			require.NoError(t, <-first)
			require.NoError(t, <-second) // reused the first connection
			close(releaseSecondDial)
			// Let the unused connection reach the server before we return.
			require.Eventually(t, func() bool { return accepted.Load() == 2 }, nestedTestTimeout, time.Millisecond)
			return nil, nil
		})
		done <- err
	}()

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(nestedTestTimeout):
		t.Fatal("invocation did not return; shutdown is waiting on the unused connection")
	}
}

// Shutdown must still wait for a request that is in flight when fn returns.
func TestServeNestedClientDrainsActiveRequest(t *testing.T) {
	entered := make(chan struct{})
	release := make(chan struct{})
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		close(entered)
		<-release
		okResponse(w)
	})}
	transport := http.DefaultTransport.(*http.Transport).Clone()

	var inflight <-chan error
	done := make(chan error, 1)
	go func() {
		_, err := serveNestedClient(t.Context(), srv, transport, func(ctx context.Context, client graphql.Client) ([]byte, error) {
			inflight = request(context.WithoutCancel(ctx), client, "Slow")
			waitFor(t, entered, "request in handler")
			return nil, nil
		})
		done <- err
	}()

	select {
	case <-done:
		t.Fatal("invocation returned while a request was still in flight")
	case <-time.After(100 * time.Millisecond):
	}
	close(release)
	require.NoError(t, <-inflight)
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(nestedTestTimeout):
		t.Fatal("invocation did not return after the request drained")
	}
}

func okResponse(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"data":{"ok":true}}`))
}

func request(ctx context.Context, client graphql.Client, op string) <-chan error {
	done := make(chan error, 1)
	go func() {
		var data struct{ OK bool }
		done <- client.MakeRequest(ctx, &graphql.Request{OpName: op, Query: "query " + op + " { ok }"}, &graphql.Response{Data: &data})
	}()
	return done
}

func waitFor(t *testing.T, ch <-chan struct{}, what string) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(nestedTestTimeout):
		t.Fatalf("timeout waiting for %s", what)
	}
}
