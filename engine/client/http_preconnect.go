package client

import (
	"context"
	"crypto/tls"
	"net"
	"sync"
	"sync/atomic"
)

// preparedHTTPDial owns one raw connection until the HTTP/2 transport claims
// it. Subsequent dials use the ordinary connector and the ordinary HTTP/2 pool.
// It sends neither a protocol preface nor a session request ahead of readiness.
type preparedHTTPDial struct {
	next    func(context.Context, string, string) (net.Conn, error)
	done    chan struct{}
	cancel  context.CancelFunc
	claimed atomic.Bool
	closed  sync.Once
	conn    net.Conn
	err     error
}

func prepareHTTPDial(ctx context.Context, dial func(context.Context, string, string) (net.Conn, error)) *preparedHTTPDial {
	ctx, cancel := context.WithCancel(ctx)
	p := &preparedHTTPDial{next: dial, done: make(chan struct{}), cancel: cancel}
	go func() {
		defer close(p.done)
		conn, err := dial(ctx, "tcp", "dagger:80")
		p.err = err
		if err != nil && conn != nil {
			conn.Close()
			conn = nil
		}
		p.conn = conn
		if conn == nil {
			cancel()
		}
	}()
	return p
}

func (p *preparedHTTPDial) dial(ctx context.Context, network, addr string) (net.Conn, error) {
	if !p.claimed.CompareAndSwap(false, true) {
		return p.next(ctx, network, addr)
	}
	select {
	case <-p.done:
	case <-ctx.Done():
		p.cancel()
		<-p.done
	}
	if ctx.Err() != nil {
		p.close()
		return nil, context.Cause(ctx)
	}
	return p.conn, p.err
}

func (p *preparedHTTPDial) closeUnused() {
	if !p.claimed.CompareAndSwap(false, true) {
		return
	}
	p.close()
}

// Abort an unused/failed preparation. No graceful TLS shutdown is necessary
// before an HTTP request is sent, and it must not block cleanup on the peer.
func (p *preparedHTTPDial) close() {
	p.closed.Do(func() {
		p.cancel()
		// Command connectors may detach from cancellation; join their result
		// and explicitly close a connection which arrives after cancellation.
		<-p.done
		if p.conn != nil {
			if secure, ok := p.conn.(*tls.Conn); ok {
				secure.NetConn().Close()
			} else {
				p.conn.Close()
			}
		}
	})
}

// Once handed off, the HTTP/2 transport owns connection shutdown. Client.Close
// releases the retained dial context only after closing that transport and
// draining telemetry; do not bypass HTTP/2's bounded TLS close implementation.
func (p *preparedHTTPDial) release() {
	if !p.claimed.Load() {
		p.closeUnused()
	}
	p.cancel()
}
