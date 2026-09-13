package server

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/dagger/dagger/engine/clientdb"
	"github.com/dagger/dagger/engine/telemetryattrs"
	bkgw "github.com/dagger/dagger/internal/buildkit/frontend/gateway/client"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

// The main CLI drains telemetry on a separate connection after /shutdown
// returns. Closing its subscription at the HTTP response loses the final
// session-complete carrier, which is not written until background teardown.
func TestMainShutdownKeepsTelemetryUntilSessionComplete(t *testing.T) {
	srv := newTeardownTestServer(t)
	sess, client := newTeardownTestSession(srv, "completion", "main", 1)
	client.shutdownCh = make(chan struct{})
	recorder := tracetest.NewSpanRecorder()
	client.tracerProvider = sdktrace.NewTracerProvider(
		sdktrace.WithSpanProcessor(srv.wcprofSpanCount),
		sdktrace.WithSpanProcessor(recorder),
	)
	t.Cleanup(func() { require.NoError(t, client.tracerProvider.Shutdown(context.Background())) })
	ctx, span := client.tracerProvider.Tracer(InstrumentationLibrary).Start(t.Context(), "query")
	sc := trace.SpanContextFromContext(ctx)
	sess.wcprofTraceID = sc.TraceID()
	sess.wcprofRootSpanID = sc.SpanID()
	span.End()

	// The request must finish even while the independently-owned teardown
	// query drain remains blocked. It must not authorize subscriber EOF yet.
	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/shutdown", nil)
	for range 2 {
		require.NoError(t, srv.serveShutdown(httptest.NewRecorder(), request, client))
	}
	select {
	case <-client.shutdownCh:
		t.Fatal("main telemetry closed before the session-complete carrier was emitted")
	default:
	}
	require.Len(t, recorder.Ended(), 1)

	releaseTeardownDrain(sess)
	sess.lifecycleMu.Lock()
	err := srv.removeDaggerSession(t.Context(), sess)
	sess.lifecycleMu.Unlock()
	require.NoError(t, err)
	select {
	case <-client.shutdownCh:
	default:
		t.Fatal("main telemetry did not close after final provider shutdown")
	}
	ended := recorder.Ended()
	require.Len(t, ended, 2)
	require.Equal(t, wcprofSessionCompleteSpanName, ended[1].Name())
	var declared string
	for _, attr := range ended[1].Attributes() {
		if string(attr.Key) == telemetryattrs.WcprofSessionSpanCountAttr {
			declared = attr.Value.AsString()
		}
	}
	require.Equal(t, "1", declared)
	require.Zero(t, srv.wcprofSpanCount.Final(sess.wcprofTraceID))
}

type subscribedRecorder struct {
	*httptest.ResponseRecorder
	ready chan struct{}
	once  sync.Once
}

func (r *subscribedRecorder) Flush() {
	r.ResponseRecorder.Flush()
	r.once.Do(func() { close(r.ready) })
}

// Exercise the real DB-backed SSE path without a network listener. Its
// connection does not own an ordinary-client reference or prevent reaping.
func TestMainTelemetrySSEDrainsFinalCarrier(t *testing.T) {
	srv := newTeardownTestServer(t)
	srv.clientDBs = clientdb.NewDBs(t.TempDir())
	srv.telemetryPubSub = NewPubSub(srv)
	sess, client := newTeardownTestSession(srv, "sse-completion", "main", 1)
	sess.telemetryPubSub = srv.telemetryPubSub
	client.tracerProvider = sdktrace.NewTracerProvider(
		sdktrace.WithSpanProcessor(srv.wcprofSpanCount),
		sdktrace.WithSyncer(srv.telemetryPubSub.Spans(client)),
	)
	t.Cleanup(func() { require.NoError(t, client.tracerProvider.Shutdown(context.Background())) })
	ctx, span := client.tracerProvider.Tracer(InstrumentationLibrary).Start(t.Context(), "query")
	sc := trace.SpanContextFromContext(ctx)
	sess.wcprofTraceID, sess.wcprofRootSpanID = sc.TraceID(), sc.SpanID()
	span.End()

	subscriptionCtx, cancel := context.WithCancel(t.Context())
	t.Cleanup(cancel)
	writer := &subscribedRecorder{ResponseRecorder: httptest.NewRecorder(), ready: make(chan struct{})}
	finished := make(chan error, 1)
	go func() {
		request := httptest.NewRequestWithContext(subscriptionCtx, http.MethodGet, "/v1/traces", nil)
		finished <- srv.telemetryPubSub.TracesSubscribeHandler(writer, request, client)
	}()
	select {
	case <-writer.ready:
	case <-time.After(10 * time.Second):
		t.Fatal("SSE subscription did not start")
	}
	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/shutdown", nil)
	require.NoError(t, srv.serveShutdown(httptest.NewRecorder(), request, client))
	releaseTeardownDrain(sess)
	// Use the actual asynchronous last-connection cleanup, not direct teardown.
	require.NoError(t, srv.releaseClientConnection(t.Context(), sess, client))
	select {
	case err := <-finished:
		require.NoError(t, err)
	case <-time.After(10 * time.Second):
		t.Fatal("SSE did not finish after the main client's last disconnect")
	}
	require.Contains(t, writer.Body.String(), wcprofSessionCompleteSpanName)
	require.Contains(t, writer.Body.String(), telemetryattrs.WcprofSessionSpanCountAttr)
	require.Eventually(t, func() bool {
		return !sessionInRegistry(srv, sess.sessionID)
	}, 10*time.Second, time.Millisecond)
}

type shutdownBarrierProcessor struct {
	*tracetest.SpanRecorder
	entered chan struct{}
	release <-chan struct{}
	err     error
}

type blockedReleaseContainer struct {
	bkgw.Container
	entered chan struct{}
	release <-chan struct{}
}

func (c *blockedReleaseContainer) Release(ctx context.Context) error {
	close(c.entered)
	select {
	case <-c.release:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func TestMainTelemetryDoesNotWaitForContainerRelease(t *testing.T) {
	srv := newTeardownTestServer(t)
	sess, client := newTeardownTestSession(srv, "container-release", "main", 0)
	release := make(chan struct{})
	var once sync.Once
	unblock := func() { once.Do(func() { close(release) }) }
	t.Cleanup(unblock)
	ctr := &blockedReleaseContainer{entered: make(chan struct{}), release: release}
	sess.containers = map[bkgw.Container]struct{}{ctr: {}}
	releaseTeardownDrain(sess)
	done := make(chan error, 1)
	go func() {
		sess.lifecycleMu.Lock()
		defer sess.lifecycleMu.Unlock()
		done <- srv.removeDaggerSession(t.Context(), sess)
	}()
	select {
	case <-ctr.entered:
	case <-time.After(10 * time.Second):
		t.Fatal("teardown did not reach container release")
	}
	select {
	case <-client.shutdownCh:
	case <-time.After(10 * time.Second):
		t.Fatal("telemetry drain is waiting for unrelated container release")
	}
	select {
	case <-done:
		t.Fatal("teardown returned before container cleanup finished")
	default:
	}
	unblock()
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(10 * time.Second):
		t.Fatal("teardown did not finish after container release")
	}
}

func TestMainTelemetryReconnectWaitsForLastDisconnect(t *testing.T) {
	srv := newTeardownTestServer(t)
	sess, client := newTeardownTestSession(srv, "telemetry-reconnect", "main", 1)
	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/shutdown", nil)
	require.NoError(t, srv.serveShutdown(httptest.NewRecorder(), request, client))
	// The surviving/reconnected ordinary connection prevents reaping, but the
	// telemetry stream itself does not hold an ordinary connection reference.
	srv.reapDaggerSession(t.Context(), sess, client)
	require.Equal(t, sessionStateInitialized, sess.state.Load())
	select {
	case <-client.shutdownCh:
		t.Fatal("telemetry ended before the surviving connection disconnected")
	default:
	}
	releaseTeardownDrain(sess)
	require.NoError(t, srv.releaseClientConnection(t.Context(), sess, client))
	select {
	case <-client.shutdownCh:
	case <-time.After(10 * time.Second):
		t.Fatal("last disconnect did not complete telemetry")
	}
	require.Eventually(t, func() bool {
		return !sessionInRegistry(srv, sess.sessionID)
	}, 10*time.Second, time.Millisecond)
}

func (p *shutdownBarrierProcessor) Shutdown(ctx context.Context) error {
	close(p.entered)
	select {
	case <-p.release:
		return p.err
	case <-ctx.Done():
		return ctx.Err()
	}
}

// A nested provider can flush to its ancestors even after the main provider
// has shut down. Subscriber EOF must follow every provider, including failures.
func TestMainTelemetryWaitsForAllProviderShutdown(t *testing.T) {
	for _, blockedClient := range []string{"main", "nested"} {
		for _, shutdownFails := range []bool{false, true} {
			name := blockedClient
			if shutdownFails {
				name += "-error"
			}
			t.Run(name, func(t *testing.T) {
				srv := newTeardownTestServer(t)
				sess, main := newTeardownTestSession(srv, name, "main", 0)
				nested := &daggerClient{clientID: "nested", daggerSession: sess, shutdownCh: make(chan struct{})}
				sess.clients[nested.clientID] = nested
				release := make(chan struct{})
				var releaseOnce sync.Once
				unblock := func() { releaseOnce.Do(func() { close(release) }) }
				t.Cleanup(unblock)
				processor := &shutdownBarrierProcessor{
					SpanRecorder: tracetest.NewSpanRecorder(), entered: make(chan struct{}), release: release,
				}
				if shutdownFails {
					processor.err = errors.New("deliberate provider shutdown failure")
				}
				sess.clients[blockedClient].tracerProvider = sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(processor))
				releaseTeardownDrain(sess)
				done := make(chan error, 1)
				go func() {
					sess.lifecycleMu.Lock()
					defer sess.lifecycleMu.Unlock()
					done <- srv.removeDaggerSession(t.Context(), sess)
				}()
				select {
				case <-processor.entered:
				case <-time.After(10 * time.Second):
					t.Fatal("teardown did not reach provider shutdown")
				}
				select {
				case <-main.shutdownCh:
					t.Fatal("main subscriber closed while a provider was still flushing")
				default:
				}
				unblock()
				select {
				case err := <-done:
					if shutdownFails {
						require.ErrorContains(t, err, processor.err.Error())
					} else {
						require.NoError(t, err)
					}
				case <-time.After(10 * time.Second):
					t.Fatal("teardown did not finish after provider shutdown")
				}
				for _, client := range []*daggerClient{main, nested} {
					select {
					case <-client.shutdownCh:
					default:
						t.Fatal("subscriber not closed after provider shutdown, including error paths")
					}
				}
			})
		}
	}
}

func TestNestedShutdownStillClosesOwnTelemetry(t *testing.T) {
	srv := newTeardownTestServer(t)
	sess, main := newTeardownTestSession(srv, "nested-completion", "main", 1)
	main.shutdownCh = make(chan struct{})
	nested := &daggerClient{
		clientID: "nested", daggerSession: sess, shutdownCh: make(chan struct{}),
	}
	sess.clients[nested.clientID] = nested
	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/shutdown", nil)
	// Nested module clients must not wait for parent teardown: the parent can
	// still be evaluating a function whose shutdown waits for this response.
	for range 2 {
		require.NoError(t, srv.serveShutdown(httptest.NewRecorder(), request, nested))
	}
	select {
	case <-nested.shutdownCh:
	default:
		t.Fatal("nested telemetry is waiting for its parent session to finish")
	}
	select {
	case <-main.shutdownCh:
		t.Fatal("nested shutdown closed main telemetry")
	default:
	}
	releaseTeardownDrain(sess)
	sess.lifecycleMu.Lock()
	err := srv.removeDaggerSession(t.Context(), sess)
	sess.lifecycleMu.Unlock()
	require.NoError(t, err)
}
