package client

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
	"golang.org/x/sync/errgroup"
)

type readinessConnector struct {
	addr  string
	mu    sync.Mutex
	conns []net.Conn
}

func (c *readinessConnector) EngineID() string { return "readiness-test" }

func (c *readinessConnector) Connect(ctx context.Context) (net.Conn, error) {
	conn, err := (&net.Dialer{}).DialContext(ctx, "tcp", c.addr)
	if err == nil {
		c.mu.Lock()
		c.conns = append(c.conns, conn)
		c.mu.Unlock()
	}
	return conn, err
}

type readinessExporter struct{ exported chan struct{} }

func (e *readinessExporter) ExportSpans(context.Context, []sdktrace.ReadOnlySpan) error {
	select {
	case e.exported <- struct{}{}:
	default:
	}
	return nil
}
func (e *readinessExporter) Shutdown(context.Context) error { return nil }

type readinessHarness struct {
	client       *Client
	initStarted  chan struct{}
	traceStarted chan struct{}
	shutdown     chan struct{}
	exported     chan struct{}
	mu           sync.Mutex
	addresses    map[string]string
	initCanceled chan struct{}
}

func newReadinessHarness(t *testing.T, mode string) *readinessHarness {
	t.Helper()
	h := &readinessHarness{
		initStarted: make(chan struct{}), traceStarted: make(chan struct{}),
		shutdown: make(chan struct{}), exported: make(chan struct{}, 1),
		addresses: map[string]string{}, initCanceled: make(chan struct{}),
	}
	var shutdownOnce sync.Once
	c := &Client{Params: Params{ID: "readiness-client", SessionID: "readiness-session", SecretToken: "readiness-secret"}}
	c.internalCtx, c.internalCancel = context.WithCancelCause(t.Context())
	c.closeCtx, c.closeRequests = context.WithCancelCause(t.Context())
	c.eg = new(errgroup.Group)
	c.EngineTrace = &readinessExporter{exported: h.exported}
	h.client = c
	await := func(r *http.Request, ready <-chan struct{}) bool {
		select {
		case <-ready:
			return true
		case <-r.Context().Done():
			return false
		case <-t.Context().Done():
			return false
		case <-time.After(3 * time.Second):
			t.Errorf("readiness barrier timed out for %s", r.URL.Path)
			return false
		}
	}
	server := httptest.NewServer(h2c.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, 2, r.ProtoMajor)
		user, password, ok := r.BasicAuth()
		assert.True(t, ok)
		assert.Equal(t, "readiness-secret", user)
		assert.Empty(t, password)
		h.mu.Lock()
		h.addresses[r.URL.Path] = r.RemoteAddr
		h.mu.Unlock()
		switch r.URL.Path {
		case engine.InitEndpoint:
			close(h.initStarted)
			if !await(r, h.traceStarted) {
				return
			}
			if mode == "cancel" || mode == "subscribe-error" {
				<-r.Context().Done()
				close(h.initCanceled)
				return
			}
			if mode == "init-error" {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			w.WriteHeader(http.StatusNoContent)
		case "/v1/traces":
			close(h.traceStarted)
			if !await(r, h.initStarted) {
				return
			}
			if mode == "subscribe-error" {
				w.WriteHeader(http.StatusForbidden)
				return
			}
			w.Header().Set("Content-Type", "text/event-stream")
			fmt.Fprint(w, "event: subscribed\ndata: ready\n\n")
			w.(http.Flusher).Flush()
			if !await(r, h.shutdown) {
				return
			}
			if !await(r, c.closeCtx.Done()) {
				return
			}
			// Deliberately emit the last event after foreground requests close.
			fmt.Fprint(w, "event: message\ndata: {}\n\n")
			w.(http.Flusher).Flush()
		case engine.ShutdownEndpoint:
			shutdownOnce.Do(func() { close(h.shutdown) })
			w.WriteHeader(http.StatusNoContent)
		case "/readiness-query":
			w.WriteHeader(http.StatusNoContent)
		default:
			http.NotFound(w, r)
		}
	}), &http2.Server{}))
	connector := &readinessConnector{addr: strings.TrimPrefix(server.URL, "http://")}
	c.connector = connector
	c.httpClient = c.newHTTPClient()
	t.Cleanup(func() {
		c.closeRequests(errors.New("test cleanup"))
		c.internalCancel(errors.New("test cleanup"))
		shutdownOnce.Do(func() { close(h.shutdown) })
		connector.mu.Lock()
		for _, conn := range connector.conns {
			conn.Close()
		}
		connector.mu.Unlock()
		server.Close()
	})
	return h
}

func TestHTTPReadinessOverlapsAndPreservesDrain(t *testing.T) {
	h := newReadinessHarness(t, "success")
	require.NoError(t, h.client.connectHTTP(t.Context()))
	// The barrier in each handler requires the other connection to have started.
	request, err := http.NewRequestWithContext(t.Context(), "POST", "http://dagger/readiness-query", nil)
	require.NoError(t, err)
	response, err := h.client.httpClient.Do(request)
	require.NoError(t, err)
	require.NoError(t, response.Body.Close())
	h.mu.Lock()
	addresses := make(map[string]string, len(h.addresses))
	for path, addr := range h.addresses {
		addresses[path] = addr
	}
	h.mu.Unlock()
	require.NotEmpty(t, addresses[engine.InitEndpoint])
	require.Equal(t, addresses[engine.InitEndpoint], addresses["/readiness-query"])
	require.NotEqual(t, addresses[engine.InitEndpoint], addresses["/v1/traces"])
	require.NoError(t, h.client.Close())
	select {
	case <-h.exported:
	default:
		t.Fatal("Close returned before the final telemetry event was exported")
	}
}

func TestHTTPReadinessSetupFailuresJoinAndClose(t *testing.T) {
	for _, mode := range []string{"init-error", "subscribe-error", "cancel"} {
		t.Run(mode, func(t *testing.T) {
			h := newReadinessHarness(t, mode)
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			if mode == "cancel" {
				go func() {
					select {
					case <-h.traceStarted:
					case <-t.Context().Done():
						return
					}
					select {
					case <-h.initStarted:
						cancel()
					case <-t.Context().Done():
					}
				}()
			}
			err := h.client.connectHTTP(ctx)
			require.Error(t, err)
			switch mode {
			case "init-error":
				require.ErrorContains(t, err, "503")
			case "subscribe-error":
				require.ErrorContains(t, err, "403")
			case "cancel":
				require.ErrorIs(t, err, context.Canceled)
			}
			require.Error(t, h.client.closeCtx.Err())
			if mode != "init-error" {
				select {
				case <-h.initCanceled:
				case <-time.After(time.Second):
					t.Fatal("initialization request was not canceled")
				}
			}
		})
	}
}

func TestHTTPReadinessWithoutTelemetryStaysLazy(t *testing.T) {
	c := &Client{}
	// No foreground transport exists: touching it would panic.
	require.NoError(t, c.connectHTTP(t.Context()))
}

func TestHTTPReadinessInitClosesRejectedBody(t *testing.T) {
	body := &readinessBody{Reader: strings.NewReader("not published")}
	c := &Client{httpClient: &httpClient{inner: &http.Client{
		Transport: readinessRoundTripper(func(*http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: 403, Status: "403 Forbidden", Body: body, Header: http.Header{}}, nil
		}),
	}}}
	require.ErrorContains(t, c.init(t.Context()), "403 Forbidden")
	require.True(t, body.closed)
}

type readinessRoundTripper func(*http.Request) (*http.Response, error)

func (f readinessRoundTripper) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type readinessBody struct {
	io.Reader
	closed bool
}

func (b *readinessBody) Close() error { b.closed = true; return nil }
