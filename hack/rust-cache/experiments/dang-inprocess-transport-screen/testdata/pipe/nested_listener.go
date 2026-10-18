package dangshared

import (
	"context"
	"net"
	"net/http"
	"sync"
	"sync/atomic"
)

// Diagnostic switch for the isolated transport screen. Both arms still use
// net/http, the same GraphQL client and the real nested API handler.
var inMemoryNestedTransport atomic.Bool

func listenNestedClient(transport *http.Transport) (net.Listener, error) {
	if !inMemoryNestedTransport.Load() {
		return net.Listen("tcp", "127.0.0.1:0")
	}
	listener := &nestedPipeListener{connections: make(chan net.Conn), closed: make(chan struct{})}
	transport.DialContext = listener.dialContext
	return listener, nil
}

type nestedPipeListener struct {
	connections chan net.Conn
	closed      chan struct{}
	once        sync.Once
}

func (l *nestedPipeListener) Accept() (net.Conn, error) {
	select {
	case <-l.closed:
		return nil, net.ErrClosed
	default:
	}
	select {
	case connection := <-l.connections:
		return connection, nil
	case <-l.closed:
		return nil, net.ErrClosed
	}
}

func (l *nestedPipeListener) Close() error {
	l.once.Do(func() { close(l.closed) })
	return nil
}

func (*nestedPipeListener) Addr() net.Addr { return nestedPipeAddr{} }

func (l *nestedPipeListener) dialContext(ctx context.Context, _, _ string) (net.Conn, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	select {
	case <-l.closed:
		return nil, net.ErrClosed
	default:
	}
	client, server := net.Pipe()
	select {
	case l.connections <- server:
		return client, nil
	case <-l.closed:
		_ = client.Close()
		_ = server.Close()
		return nil, net.ErrClosed
	case <-ctx.Done():
		_ = client.Close()
		_ = server.Close()
		return nil, ctx.Err()
	}
}

type nestedPipeAddr struct{}

func (nestedPipeAddr) Network() string { return "pipe" }
func (nestedPipeAddr) String() string  { return "127.0.0.1:0" }
