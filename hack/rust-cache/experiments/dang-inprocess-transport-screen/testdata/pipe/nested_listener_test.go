package dangshared

import (
	"context"
	"io"
	"net"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestNestedPipeListener(t *testing.T) {
	t.Run("round trip", func(t *testing.T) {
		listener := &nestedPipeListener{connections: make(chan net.Conn), closed: make(chan struct{})}
		t.Cleanup(func() { _ = listener.Close() })
		serverDone := make(chan error, 1)
		go func() {
			connection, err := listener.Accept()
			if err != nil {
				serverDone <- err
				return
			}
			defer connection.Close()
			_, err = io.CopyN(connection, connection, 4)
			serverDone <- err
		}()
		client, err := listener.dialContext(t.Context(), "tcp", "127.0.0.1:0")
		require.NoError(t, err)
		defer client.Close()
		_, err = client.Write([]byte("ping"))
		require.NoError(t, err)
		var received [4]byte
		_, err = io.ReadFull(client, received[:])
		require.NoError(t, err)
		require.Equal(t, "ping", string(received[:]))
		require.NoError(t, <-serverDone)
	})
	t.Run("cancel pending dial", func(t *testing.T) {
		listener := &nestedPipeListener{connections: make(chan net.Conn), closed: make(chan struct{})}
		defer listener.Close()
		ctx, cancel := context.WithCancel(t.Context())
		done := make(chan error, 1)
		go func() {
			_, err := listener.dialContext(ctx, "tcp", "127.0.0.1:0")
			done <- err
		}()
		cancel()
		require.ErrorIs(t, <-done, context.Canceled)
	})
	t.Run("close wakes accept and dial", func(t *testing.T) {
		listener := &nestedPipeListener{connections: make(chan net.Conn), closed: make(chan struct{})}
		accepted, dialed := make(chan error, 1), make(chan error, 1)
		go func() { _, err := listener.Accept(); accepted <- err }()
		// A different listener keeps this dial pending rather than pairing it
		// with the accept above.
		dialListener := &nestedPipeListener{connections: make(chan net.Conn), closed: make(chan struct{})}
		go func() { _, err := dialListener.dialContext(t.Context(), "tcp", "127.0.0.1:0"); dialed <- err }()
		require.NoError(t, listener.Close())
		require.NoError(t, listener.Close())
		require.NoError(t, dialListener.Close())
		require.ErrorIs(t, <-accepted, net.ErrClosed)
		require.ErrorIs(t, <-dialed, net.ErrClosed)
		_, err := listener.Accept()
		require.ErrorIs(t, err, net.ErrClosed)
		_, err = dialListener.dialContext(t.Context(), "tcp", "127.0.0.1:0")
		require.ErrorIs(t, err, net.ErrClosed)
	})
}
