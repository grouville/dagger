package client

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type countedHTTPConn struct {
	net.Conn
	closes atomic.Int32
}

func (c *countedHTTPConn) Close() error {
	c.closes.Add(1)
	return c.Conn.Close()
}

func preconnectPipe(t *testing.T) *countedHTTPConn {
	t.Helper()
	a, b := net.Pipe()
	t.Cleanup(func() { a.Close(); b.Close() })
	return &countedHTTPConn{Conn: a}
}

func TestPreparedHTTPDialHandsOffOnce(t *testing.T) {
	first, second := preconnectPipe(t), preconnectPipe(t)
	var calls atomic.Int32
	var firstCtx context.Context
	p := prepareHTTPDial(t.Context(), func(ctx context.Context, network, addr string) (net.Conn, error) {
		require.Equal(t, "tcp", network)
		require.Equal(t, "dagger:80", addr)
		if calls.Add(1) == 1 {
			firstCtx = ctx
			return first, nil
		}
		return second, nil
	})
	defer p.closeUnused()
	conn, err := p.dial(t.Context(), "tcp", "dagger:80")
	require.NoError(t, err)
	p.closeUnused()
	require.NoError(t, firstCtx.Err(), "cleanup must not cancel transferred telemetry")
	require.Zero(t, first.closes.Load())
	next, err := p.dial(t.Context(), "tcp", "dagger:80")
	require.NoError(t, err)
	require.Same(t, second, next, "reconnects must use the normal connector")
	require.EqualValues(t, 2, calls.Load())
	require.Same(t, first, conn)
	p.close()
	p.close()
	require.ErrorIs(t, firstCtx.Err(), context.Canceled)
	require.EqualValues(t, 1, first.closes.Load())
}

func TestPreparedHTTPDialPreservesTLSState(t *testing.T) {
	for _, secure := range []bool{false, true} {
		var raw net.Conn = preconnectPipe(t)
		if secure {
			raw = tls.Client(raw, &tls.Config{ServerName: "test.invalid", MinVersion: tls.VersionTLS12})
		}
		p := prepareHTTPDial(t.Context(), func(context.Context, string, string) (net.Conn, error) { return raw, nil })
		conn, err := p.dial(t.Context(), "tcp", "dagger:80")
		require.NoError(t, err)
		_, ok := conn.(*tls.Conn)
		require.Equal(t, secure, ok)
		require.Same(t, raw, conn)
		p.close()
	}
}

func TestPreparedHTTPDialReleaseLeavesShutdownToTransport(t *testing.T) {
	raw := preconnectPipe(t)
	var dialCtx context.Context
	p := prepareHTTPDial(t.Context(), func(ctx context.Context, _, _ string) (net.Conn, error) {
		dialCtx = ctx
		return raw, nil
	})
	conn, err := p.dial(t.Context(), "tcp", "dagger:80")
	require.NoError(t, err)
	p.release()
	require.ErrorIs(t, dialCtx.Err(), context.Canceled)
	require.Zero(t, raw.closes.Load(), "HTTP/2 owns shutdown after handoff")
	require.NoError(t, conn.Close())
}

func TestPreparedHTTPDialAbortDoesNotWaitForTLSPeer(t *testing.T) {
	certServer := httptest.NewTLSServer(http.NotFoundHandler())
	defer certServer.Close()
	clientEnd, serverEnd := net.Pipe()
	defer clientEnd.Close()
	defer serverEnd.Close()
	config := certServer.Client().Transport.(*http.Transport).TLSClientConfig.Clone()
	config.ServerName = "127.0.0.1"
	clientTLS := tls.Client(clientEnd, config)
	serverTLS := tls.Server(serverEnd, certServer.TLS)
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Second)
	defer cancel()
	serverReady := make(chan error, 1)
	go func() { serverReady <- serverTLS.HandshakeContext(ctx) }()
	require.NoError(t, clientTLS.HandshakeContext(ctx))
	require.NoError(t, <-serverReady)
	// The handshake completed, but the peer deliberately never reads again.
	// tls.Conn.Close would block writing close_notify into the unbuffered pipe.
	p := prepareHTTPDial(ctx, func(context.Context, string, string) (net.Conn, error) { return clientTLS, nil })
	<-p.done
	done := make(chan struct{})
	go func() { p.closeUnused(); close(done) }()
	select {
	case <-done:
	case <-ctx.Done():
		t.Fatal("aborting an unused TLS connection waited for the peer")
	}
}

func TestPreparedHTTPDialClosesLateUnclaimedConnection(t *testing.T) {
	conn := preconnectPipe(t)
	started := make(chan struct{})
	p := prepareHTTPDial(t.Context(), func(ctx context.Context, _, _ string) (net.Conn, error) {
		close(started)
		<-ctx.Done()
		// Model a command connector that returns a live pipe after cancellation.
		return conn, nil
	})
	<-started
	p.closeUnused()
	p.closeUnused()
	require.EqualValues(t, 1, conn.closes.Load())
}

func TestPreparedHTTPDialCanceledConsumerJoinsAndCloses(t *testing.T) {
	conn := preconnectPipe(t)
	started := make(chan struct{})
	p := prepareHTTPDial(t.Context(), func(ctx context.Context, _, _ string) (net.Conn, error) {
		close(started)
		<-ctx.Done()
		return conn, nil
	})
	defer p.closeUnused()
	<-started
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	got, err := p.dial(ctx, "tcp", "dagger:80")
	require.ErrorIs(t, err, context.Canceled)
	require.Nil(t, got)
	require.EqualValues(t, 1, conn.closes.Load())
}

func TestPreparedHTTPDialErrorAndReconnect(t *testing.T) {
	errDial := errors.New("dial failed")
	bad, good := preconnectPipe(t), preconnectPipe(t)
	var calls atomic.Int32
	p := prepareHTTPDial(t.Context(), func(context.Context, string, string) (net.Conn, error) {
		if calls.Add(1) == 1 {
			return bad, errDial
		}
		return good, nil
	})
	defer p.closeUnused()
	got, err := p.dial(t.Context(), "tcp", "dagger:80")
	require.ErrorIs(t, err, errDial)
	require.Nil(t, got)
	require.EqualValues(t, 1, bad.closes.Load())
	got, err = p.dial(t.Context(), "tcp", "dagger:80")
	require.NoError(t, err)
	require.Same(t, good, got)
}

func TestPreparedHTTPTransportsSendNothingUntilClaimedAndDrain(t *testing.T) {
	h := newReadinessHarness(t, "success")
	foreground := prepareHTTPDial(t.Context(), h.client.DialContext)
	defer foreground.closeUnused()
	telemetry := prepareHTTPDial(context.WithoutCancel(t.Context()), func(ctx context.Context, _, _ string) (net.Conn, error) {
		return h.client.dialContextNoClientClose(ctx)
	})
	defer telemetry.closeUnused()
	<-foreground.done
	<-telemetry.done
	require.NoError(t, foreground.err)
	require.NoError(t, telemetry.err)
	select {
	case <-h.initStarted:
		t.Fatal("raw preparation sent an init request")
	case <-h.traceStarted:
		t.Fatal("raw preparation sent a telemetry request")
	default:
	}
	h.client.httpClient = h.client.newHTTPClientWithDial(foreground.dial)
	h.client.preparedHTTPDials = []*preparedHTTPDial{foreground, telemetry}
	h.client.preparedTelemetryHTTP = h.client.newHTTPClientWithDial(telemetry.dial)
	require.NoError(t, h.client.connectHTTPWithTelemetry(t.Context(), h.client.preparedTelemetryHTTP))
	foreground.closeUnused()
	telemetry.closeUnused()
	require.NoError(t, h.client.Close())
	select {
	case <-h.exported:
	case <-time.After(3 * time.Second):
		t.Fatal("telemetry did not drain after foreground close")
	}
}
