package attachables

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"

	"github.com/dagger/dagger/engine"
	telemetry "github.com/dagger/otel-go"
	"go.opentelemetry.io/otel/propagation"
	"golang.org/x/net/http2"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
)

// Preserve the existing provider instrumentation scope across the package move.
const InstrumentationLibrary = "dagger.io/engine.client"

type SessionAttachable interface {
	Register(*grpc.Server)
}

func ConnectSessionAttachables(
	ctx context.Context,
	conn net.Conn,
	headers http.Header,
	attachables ...SessionAttachable,
) (*SessionAttachablesServer, error) {
	sessionSrv := NewSessionAttachablesServer(ctx, conn, attachables...)
	for _, methodURL := range sessionSrv.MethodURLs {
		headers.Add(engine.SessionMethodNameMetaKey, methodURL)
	}
	telemetry.Propagator.Inject(ctx, propagation.HeaderCarrier(headers))

	req := &http.Request{
		Method: http.MethodGet,
		URL: &url.URL{
			Scheme: "http",
			Host:   "dagger",
			Path:   engine.SessionAttachablesEndpoint,
		},
		Header: headers,
		Host:   "dagger",
	}
	if err := req.Write(conn); err != nil {
		return nil, fmt.Errorf("write request: %w", err)
	}

	resp, err := http.ReadResponse(bufio.NewReader(conn), req)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}
	if resp.Body != nil {
		defer resp.Body.Close()
	}
	if resp.StatusCode != http.StatusSwitchingProtocols {
		var respBody []byte
		if resp.Body != nil {
			respBody, _ = io.ReadAll(resp.Body)
		}
		return nil, fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(respBody))
	}

	// We tell the server that we have fully read the response and will now switch to serving gRPC
	// by sending a single byte ack. This prevents the server from starting to send gRPC client
	// traffic while we are still reading the previous HTTP response.
	if _, err := conn.Write([]byte{0}); err != nil {
		return nil, fmt.Errorf("write ack: %w", err)
	}

	return sessionSrv, nil
}

func NewSessionAttachablesServer(ctx context.Context, conn net.Conn, attachables ...SessionAttachable) *SessionAttachablesServer {
	srv := grpc.NewServer()
	grpc_health_v1.RegisterHealthServer(srv, health.NewServer())
	for _, attachable := range attachables {
		attachable.Register(srv)
	}

	var methodURLs []string
	for name, svc := range srv.GetServiceInfo() {
		for _, method := range svc.Methods {
			methodURLs = append(methodURLs, sessionMethodURL(name, method.Name))
		}
	}

	return &SessionAttachablesServer{
		Server:      srv,
		Attachables: attachables,
		MethodURLs:  methodURLs,
		Conn:        conn,
	}
}

func sessionMethodURL(service, method string) string {
	return "/" + service + "/" + method
}

type SessionAttachablesServer struct {
	*grpc.Server
	MethodURLs  []string
	Conn        net.Conn
	Attachables []SessionAttachable
}

func (srv *SessionAttachablesServer) Run(ctx context.Context) {
	defer srv.Conn.Close()
	defer srv.Stop()

	doneCh := make(chan struct{})
	go func() {
		defer close(doneCh)
		(&http2.Server{}).ServeConn(srv.Conn, &http2.ServeConnOpts{
			Context: ctx,
			Handler: srv.Server,
		})
	}()

	select {
	case <-ctx.Done():
	case <-doneCh:
	}
}
