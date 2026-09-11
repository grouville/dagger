package dangshared

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/Khan/genqlient/graphql"
)

// nestedClientServer owns the server and connection pool for one invocation.
// No new requests may start after the callback returns; admitted requests drain
// during shutdown.
type nestedClientServer struct {
	server    *http.Server
	transport *http.Transport
}

func newNestedClientServer(handler http.Handler) *nestedClientServer {
	return &nestedClientServer{
		server: &http.Server{
			ReadHeaderTimeout: 10 * time.Second,
			Handler:           handler,
		},
		transport: http.DefaultTransport.(*http.Transport).Clone(),
	}
}

func (s *nestedClientServer) withClient(
	ctx context.Context,
	fn func(context.Context, graphql.Client) ([]byte, error),
) ([]byte, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("listen: %w", err)
	}
	defer l.Close()
	defer func() {
		// Concurrent requests can reuse an idle connection while their dial
		// completes in the background. Close these unused connections (and
		// cancel unused dials) before Shutdown, which otherwise gives a new
		// connection five seconds to send its first request. This pool belongs
		// only to this invocation; active requests still drain gracefully.
		s.transport.CloseIdleConnections()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer shutdownCancel()
		_ = s.server.Shutdown(shutdownCtx)
	}()

	srvErrCh := make(chan error, 1)
	go func() {
		err := s.server.Serve(l)
		if err != nil && !errors.Is(err, http.ErrServerClosed) && !errors.Is(err, net.ErrClosed) {
			srvErrCh <- err
		}
		close(srvErrCh)
	}()

	gqlClient := graphql.NewClient(fmt.Sprintf("http://%s/query", l.Addr()), &http.Client{Transport: s.transport})
	out, err := fn(ctx, gqlClient)
	if err != nil {
		return nil, err
	}
	if err := checkServerError(srvErrCh); err != nil {
		return nil, err
	}
	return out, nil
}

func checkServerError(srvErrCh <-chan error) error {
	select {
	case serveErr, ok := <-srvErrCh:
		if ok && serveErr != nil {
			return fmt.Errorf("serve nested client: %w", serveErr)
		}
	default:
	}
	return nil
}
