package engine

import (
	"bufio"
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

	// The wrong token is closed by the engine on the bad proof, so the
	// client sees the handshake end; nothing reaches Accept.
	_, err = EndpointTokenDial("tcp", addr, "wrong", time.Second)
	require.ErrorContains(t, err, "engine handshake")

	// No handshake at all: the engine closes after its window; nothing is
	// served. Use a short read to observe the close.
	raw, err := net.Dial("tcp", addr)
	require.NoError(t, err)
	_, _ = raw.Write([]byte("GET / HTTP/1.0\r\n\r\n"))
	_ = raw.SetReadDeadline(time.Now().Add(2 * time.Second))
	r := bufio.NewReader(raw)
	line, _ := r.ReadString('\n')
	require.Contains(t, line, "DAGGER-ENGINE-CHALLENGE ", "the engine only ever sends a challenge")
	_, err = r.ReadString('\n')
	require.Error(t, err, "a bad proof line closes the connection")
	raw.Close()

	// The right token gets through, with the bytes after the handshake intact.
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

// A process that binds the engine's port while the engine is down must not
// learn the token and must not pass for the engine.
func TestEndpointHandshakeRejectsImpostor(t *testing.T) {
	impostor, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer impostor.Close()
	seen := make(chan string, 1)
	go func() {
		conn, err := impostor.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		// Send a plausible challenge, record what the client sends, answer
		// with a proof it cannot compute.
		_, _ = conn.Write([]byte("DAGGER-ENGINE-CHALLENGE 00112233445566778899aabbccddeeff\n"))
		line, _ := bufio.NewReader(conn).ReadString('\n')
		seen <- line
		_, _ = conn.Write([]byte("DAGGER-ENGINE-OK 00\n"))
	}()

	_, err = EndpointTokenDial("tcp", impostor.Addr().String(), "s3cret", time.Second)
	require.ErrorContains(t, err, "does not hold the engine token")
	line := <-seen
	require.NotContains(t, line, "s3cret", "the token itself is never sent")
	require.Contains(t, line, "DAGGER-ENGINE-PROOF ")
}
