package engine

import (
	"io"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestTokenListener(t *testing.T) {
	inner, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	l := NewTokenListener(inner, "s3cret")
	defer l.Close()
	addr := l.Addr().String()

	accepted := make(chan string, 1)
	go func() {
		conn, err := l.Accept()
		if err != nil {
			accepted <- "accept error: " + err.Error()
			return
		}
		defer conn.Close()
		buf, _ := io.ReadAll(io.LimitReader(conn, 5))
		accepted <- string(buf)
	}()

	// The wrong token is closed without reaching Accept.
	bad, err := net.Dial("tcp", addr)
	require.NoError(t, err)
	require.NoError(t, WriteEndpointToken(bad, "wrong"))
	_ = bad.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, err = bad.Read(make([]byte, 1))
	require.Error(t, err, "rejected connections are closed")
	bad.Close()

	// The right token gets through, with the bytes after the preamble intact.
	good, err := EndpointTokenDial("tcp", addr, "s3cret", time.Second)
	require.NoError(t, err)
	_, err = good.Write([]byte("hello"))
	require.NoError(t, err)
	select {
	case got := <-accepted:
		require.Equal(t, "hello", got)
	case <-time.After(3 * time.Second):
		t.Fatal("accepted connection never delivered")
	}
	good.Close()
}
