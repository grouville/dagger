package dangshared

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Khan/genqlient/graphql"
)

// This is a functional bound, not a latency target. In particular, an unused
// StateNew connection must not wait for net/http's five-second shutdown grace.
const nestedClientTestTimeout = 3 * time.Second

func TestNestedClientServerSpeculativeConnection(t *testing.T) {
	callbackErr := errors.New("callback failed")
	for _, mode := range []string{"success", "callback error", "cancellation"} {
		t.Run(mode, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			f := newNestedSpeculation(t, ctx)
			f.completeDial(t)

			var wantErr error
			switch mode {
			case "callback error":
				wantErr = callbackErr
			case "cancellation":
				cancel()
				wantErr = ctx.Err()
			}
			f.invocation.finish(wantErr)
			f.invocation.wait(t, wantErr)
			f.invocation.states.wait(t, "all invocation connections closed", func(s nestedConnSnapshot) bool {
				return s.New+s.Active+s.Idle == 0
			})
			if got := f.requests.Load(); got != 2 {
				t.Fatalf("requests = %d, want 2; unused connection must not receive a request", got)
			}
		})
	}
}

func TestNestedClientServerCancelsUnusedLateDial(t *testing.T) {
	f := newNestedSpeculation(t, context.Background())
	// Both requests completed on the first connection. Their second dial is
	// still blocked, and its context is detached from request cancellation.
	f.invocation.finish(nil)
	f.invocation.wait(t, nil)
	waitNestedSignal(t, f.dialDone, "unused in-progress dial canceled")
	if !f.dialCanceled.Load() {
		t.Fatal("unused dial completed without being canceled by transport cleanup")
	}
	if got := f.invocation.states.snapshot().Accepted; got != 1 {
		t.Fatalf("accepted connections = %d, want 1", got)
	}
}

func TestNestedClientServerDrainsActiveRequest(t *testing.T) {
	for _, cancelParent := range []bool{false, true} {
		t.Run(fmt.Sprintf("canceled_parent=%t", cancelParent), func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			entered := make(chan struct{})
			release := newNestedBarrier(t)
			invocation := newNestedInvocation(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				close(entered)
				select {
				case <-release.ch:
					writeNestedResponse(w)
				case <-r.Context().Done():
				}
			}))
			invocation.start(t, ctx)
			// Deliberately independent of the callback's context: canceling that
			// context must not cancel the grace period for admitted requests.
			response := nestedRequest(invocation.client, "Active")
			waitNestedSignal(t, entered, "active request entered handler")
			invocation.states.wait(t, "active connection", func(s nestedConnSnapshot) bool { return s.Active == 1 })
			var wantErr error
			if cancelParent {
				cancel()
				wantErr = ctx.Err()
			}
			invocation.finish(wantErr)
			waitNestedSignal(t, invocation.shutdownStarted, "graceful shutdown started")
			if s := invocation.states.snapshot(); s.Active != 1 {
				t.Fatalf("active request interrupted during shutdown: %+v", s)
			}
			// Hold the handler briefly after shutdown starts so an immediate
			// return (for example, from inheriting the canceled parent context)
			// cannot race past a single nonblocking assertion.
			select {
			case <-invocation.done:
				t.Fatal("invocation returned before its active handler drained")
			case err := <-response:
				t.Fatalf("request returned before handler release: %v", err)
			case <-time.After(50 * time.Millisecond):
			}
			release.open()
			waitNestedRequest(t, response, "active request drained")
			invocation.wait(t, wantErr)
		})
	}
}

func TestNestedClientServerTransportIsolation(t *testing.T) {
	first := newNestedSpeculation(t, context.Background())
	second := newNestedSpeculation(t, context.Background())
	first.completeDial(t)
	second.completeDial(t)
	if first.invocation.owner.transport == second.invocation.owner.transport {
		t.Fatal("invocations share a transport")
	}
	if first.invocation.owner.transport == http.DefaultTransport || second.invocation.owner.transport == http.DefaultTransport {
		t.Fatal("invocation owns the global default transport")
	}
	before := second.invocation.states.snapshot()
	first.invocation.finish(nil)
	first.invocation.wait(t, nil)
	if after := second.invocation.states.snapshot(); after != before {
		t.Fatalf("first cleanup changed second invocation: before=%+v after=%+v", before, after)
	}
	waitNestedRequest(t, nestedRequest(second.invocation.client, "StillUsable"), "other invocation remains usable")
	second.invocation.states.wait(t, "other invocation idle", func(s nestedConnSnapshot) bool { return s.Active == 0 })
	if after := second.invocation.states.snapshot(); after.Accepted != before.Accepted {
		t.Fatalf("other invocation needed a replacement connection: before=%+v after=%+v", before, after)
	}
	second.invocation.finish(nil)
	second.invocation.wait(t, nil)
}

type nestedSpeculation struct {
	invocation   *nestedInvocation
	requests     atomic.Int64
	releaseDial  *nestedBarrier
	dialDone     chan struct{}
	dialCanceled atomic.Bool
}

func newNestedSpeculation(t *testing.T, ctx context.Context) *nestedSpeculation {
	t.Helper()
	firstEntered := make(chan struct{})
	releaseFirst := newNestedBarrier(t)
	f := &nestedSpeculation{releaseDial: newNestedBarrier(t), dialDone: make(chan struct{})}
	f.invocation = newNestedInvocation(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request graphql.Request
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		f.requests.Add(1)
		if request.OpName == "First" {
			close(firstEntered)
			select {
			case <-releaseFirst.ch:
			case <-r.Context().Done():
				return
			}
		}
		writeNestedResponse(w)
	}))
	dialStarted := make(chan struct{})
	var dials atomic.Int64
	dial := f.invocation.owner.transport.DialContext
	if dial == nil {
		dial = (&net.Dialer{Timeout: nestedClientTestTimeout}).DialContext
	}
	f.invocation.owner.transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		if dials.Add(1) == 2 {
			defer close(f.dialDone)
			close(dialStarted)
			select {
			case <-f.releaseDial.ch:
			case <-ctx.Done():
				f.dialCanceled.Store(true)
				return nil, ctx.Err()
			}
		}
		return dial(ctx, network, address)
	}
	f.invocation.start(t, ctx)
	first := nestedRequest(f.invocation.client, "First")
	waitNestedSignal(t, firstEntered, "first request holds connection")
	second := nestedRequest(f.invocation.client, "Second")
	// This barrier also proves that the GraphQL client actually uses the
	// production owner's transport, not a separately created or global one.
	waitNestedSignal(t, dialStarted, "second request reached owned transport's dial")
	releaseFirst.open()
	waitNestedRequest(t, first, "first response")
	waitNestedRequest(t, second, "second response reused first connection")
	f.invocation.states.wait(t, "two responses on one connection", func(s nestedConnSnapshot) bool {
		return s.Accepted == 1 && s.Idle == 1 && s.New == 0 && s.Active == 0
	})
	if got := f.requests.Load(); got != 2 {
		t.Fatalf("requests = %d, want 2 before completing speculative dial", got)
	}
	return f
}

func (f *nestedSpeculation) completeDial(t *testing.T) {
	t.Helper()
	f.releaseDial.open()
	waitNestedSignal(t, f.dialDone, "speculative dial completed")
	f.invocation.states.wait(t, "unused StateNew connection with no active requests", func(s nestedConnSnapshot) bool {
		return s.Accepted == 2 && s.New == 1 && s.Idle == 1 && s.Active == 0
	})
}

type nestedCallResult struct {
	value []byte
	err   error
}

type nestedInvocation struct {
	owner           *nestedClientServer
	states          *nestedConnStates
	client          graphql.Client
	callbackReturn  chan error
	abort           chan struct{}
	done            chan struct{}
	shutdownStarted chan struct{}
	started         bool
	result          nestedCallResult
}

func newNestedInvocation(t *testing.T, handler http.Handler) *nestedInvocation {
	t.Helper()
	f := &nestedInvocation{
		owner:           newNestedClientServer(handler),
		states:          &nestedConnStates{connections: make(map[net.Conn]http.ConnState), changed: make(chan struct{}, 1)},
		callbackReturn:  make(chan error, 1),
		abort:           make(chan struct{}),
		done:            make(chan struct{}),
		shutdownStarted: make(chan struct{}),
	}
	if f.owner.server == nil || f.owner.transport == nil {
		t.Fatal("nested client constructor did not initialize server and transport")
	}
	if f.owner.transport == http.DefaultTransport {
		t.Fatal("nested client constructor returned the global transport; refusing to configure it")
	}
	f.owner.server.ConnState = f.states.change
	f.owner.server.RegisterOnShutdown(func() { close(f.shutdownStarted) })
	t.Cleanup(func() {
		close(f.abort)
		// Only fallback cleanup: assertions must observe production teardown
		// before the test returns. In particular, this cannot make them pass.
		f.owner.transport.CloseIdleConnections()
		_ = f.owner.server.Close()
		if f.started {
			waitNestedSignal(t, f.done, "invocation goroutine stopped")
		}
	})
	return f
}

func (f *nestedInvocation) start(t *testing.T, ctx context.Context) {
	t.Helper()
	ready := make(chan graphql.Client, 1)
	f.started = true
	go func() {
		f.result.value, f.result.err = f.owner.withClient(ctx, func(_ context.Context, client graphql.Client) ([]byte, error) {
			ready <- client
			select {
			case err := <-f.callbackReturn:
				return []byte("callback result"), err
			case <-f.abort:
				return nil, context.Canceled
			}
		})
		close(f.done)
	}()
	select {
	case f.client = <-ready:
	case <-f.done:
		t.Fatalf("invocation stopped before callback: %v", f.result.err)
	case <-time.After(nestedClientTestTimeout):
		t.Fatal("timeout waiting for GraphQL client")
	}
}

func (f *nestedInvocation) finish(err error) { f.callbackReturn <- err }

func (f *nestedInvocation) wait(t *testing.T, wantErr error) {
	t.Helper()
	waitNestedSignal(t, f.done, "invocation cleanup")
	if !errors.Is(f.result.err, wantErr) {
		t.Fatalf("invocation error = %v, want %v", f.result.err, wantErr)
	}
	if wantErr == nil && string(f.result.value) != "callback result" {
		t.Fatalf("invocation result = %q, want callback result", f.result.value)
	}
}

type nestedConnSnapshot struct{ Accepted, New, Active, Idle int }

type nestedConnStates struct {
	mu          sync.Mutex
	connections map[net.Conn]http.ConnState
	accepted    int
	changed     chan struct{}
}

func (s *nestedConnStates) change(conn net.Conn, state http.ConnState) {
	s.mu.Lock()
	if state == http.StateNew {
		s.accepted++
	}
	if state == http.StateClosed || state == http.StateHijacked {
		delete(s.connections, conn)
	} else {
		s.connections[conn] = state
	}
	s.mu.Unlock()
	select {
	case s.changed <- struct{}{}:
	default:
	}
}

func (s *nestedConnStates) snapshot() nestedConnSnapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := nestedConnSnapshot{Accepted: s.accepted}
	for _, state := range s.connections {
		switch state {
		case http.StateNew:
			out.New++
		case http.StateActive:
			out.Active++
		case http.StateIdle:
			out.Idle++
		}
	}
	return out
}

func (s *nestedConnStates) wait(t *testing.T, label string, ready func(nestedConnSnapshot) bool) {
	t.Helper()
	timer := time.NewTimer(nestedClientTestTimeout)
	defer timer.Stop()
	for {
		if ready(s.snapshot()) {
			return
		}
		select {
		case <-s.changed:
		case <-timer.C:
			t.Fatalf("timeout waiting for %s: %+v", label, s.snapshot())
		}
	}
}

type nestedBarrier struct {
	once sync.Once
	ch   chan struct{}
}

func newNestedBarrier(t *testing.T) *nestedBarrier {
	t.Helper()
	b := &nestedBarrier{ch: make(chan struct{})}
	t.Cleanup(b.open)
	return b
}

func (b *nestedBarrier) open() { b.once.Do(func() { close(b.ch) }) }

func writeNestedResponse(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"data":{"ok":true}}`))
}

func nestedRequest(client graphql.Client, operation string) <-chan error {
	done := make(chan error, 1)
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), nestedClientTestTimeout)
		defer cancel()
		var data struct{ OK bool }
		err := client.MakeRequest(ctx, &graphql.Request{OpName: operation, Query: "query " + operation + " { ok }"}, &graphql.Response{Data: &data})
		if err == nil && !data.OK {
			err = errors.New("GraphQL response did not contain expected data")
		}
		done <- err
	}()
	return done
}

func waitNestedSignal(t *testing.T, ch <-chan struct{}, label string) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(nestedClientTestTimeout):
		t.Fatalf("timeout waiting for %s", label)
	}
}

func waitNestedRequest(t *testing.T, ch <-chan error, label string) {
	t.Helper()
	select {
	case err := <-ch:
		if err != nil {
			t.Fatalf("%s: %v", label, err)
		}
	case <-time.After(nestedClientTestTimeout):
		t.Fatalf("timeout waiting for %s", label)
	}
}
