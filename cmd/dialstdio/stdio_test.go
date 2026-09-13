package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/docker/cli/cli/connhelper/commandconn"
	"github.com/stretchr/testify/require"
)

// This child runs the real Cobra command and stdio copier in a separate process.
// Its one test-only readiness line is consumed before any protocol bytes.
func TestDialStdioProcess(t *testing.T) {
	if os.Getenv("DAGGER_TEST_DIALSTDIO_CHILD") != "1" {
		return
	}
	rootCmd.SetArgs([]string{"--addr", os.Getenv("DAGGER_TEST_DIALSTDIO_ADDR"), "--timeout", os.Getenv("DAGGER_TEST_DIALSTDIO_TIMEOUT")})
	fmt.Fprintln(os.Stdout, os.Getpid())
	main()
	os.Exit(0)
}

func TestDialStdioHalfClosesAfterSocketReadiness(t *testing.T) {
	for _, stdinFirst := range []bool{true, false} {
		name := "server-finishes-with-stdin-open"
		if stdinFirst {
			name = "stdin-finishes-before-server"
		}
		t.Run(name, func(t *testing.T) {
			path := unixSocketPath(t)
			conn, reader, _ := startStdioTestConn(t, t.Context(), path, 2)
			future := startUnixListenerAfter(t, path, false, 40*time.Millisecond)
			<-future.done
			require.NoError(t, future.err)
			listener := future.listener.(*net.UnixListener)
			require.NoError(t, listener.SetDeadline(time.Now().Add(time.Second)))
			server, err := listener.AcceptUnix()
			require.NoError(t, err)
			t.Cleanup(func() { server.Close() })
			require.NoError(t, server.SetDeadline(time.Now().Add(2*time.Second)))
			_, err = conn.Write([]byte("request"))
			require.NoError(t, err)
			request := make([]byte, len("request"))
			_, err = io.ReadFull(server, request)
			require.NoError(t, err)
			require.Equal(t, "request", string(request))
			if stdinFirst {
				require.NoError(t, conn.(interface{ CloseWrite() error }).CloseWrite())
				rest, err := io.ReadAll(server)
				require.NoError(t, err)
				require.Empty(t, rest)
			}
			_, err = server.Write([]byte("response"))
			require.NoError(t, err)
			require.NoError(t, server.CloseWrite())
			// EOF also waits for a successful child exit through commandconn.
			require.Equal(t, "response", readStdioToEOF(t, reader))
		})
	}
}

func TestDialStdioCloseWhileWaiting(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	t.Cleanup(cancel)
	conn, reader, pid := startStdioTestConn(t, ctx, unixSocketPath(t), 5)
	done := make(chan error, 1)
	go func() {
		_, err := reader.ReadByte()
		done <- err
	}()
	assertWaiting := func() {
		t.Helper()
		select {
		case err := <-done:
			t.Fatalf("helper exited instead of waiting for its socket: %v", err)
		case <-time.After(75 * time.Millisecond):
		}
	}
	assertWaiting()
	cancel()
	// commandconn intentionally gives the connection, not its constructor's
	// context, ownership of the child. This does not test Docker exec forwarding.
	assertWaiting()
	require.NoError(t, syscall.Kill(pid, 0))
	started := time.Now()
	require.NoError(t, conn.Close())
	require.Less(t, time.Since(started), 500*time.Millisecond)
	select {
	case err := <-done:
		require.Error(t, err)
	case <-time.After(time.Second):
		t.Fatal("closing the connection did not release its reader")
	}
	require.ErrorIs(t, syscall.Kill(pid, 0), syscall.ESRCH, "Close must reap its own helper process")
}

func TestDialStdioMissingSocketExitsWithinBudget(t *testing.T) {
	path := unixSocketPath(t)
	conn, reader, pid := startStdioTestConn(t, t.Context(), path, 1)
	started := time.Now()
	done := make(chan error, 1)
	go func() {
		_, err := io.ReadAll(reader)
		done <- err
	}()
	select {
	case err := <-done:
		require.ErrorContains(t, err, "i/o timeout")
		require.ErrorContains(t, err, path)
		require.GreaterOrEqual(t, time.Since(started), 900*time.Millisecond)
	case <-time.After(2500 * time.Millisecond):
		conn.Close()
		t.Fatal("helper did not exit within the connection budget")
	}
	require.ErrorIs(t, syscall.Kill(pid, 0), syscall.ESRCH)
}

func startStdioTestConn(t *testing.T, ctx context.Context, path string, seconds int) (net.Conn, *bufio.Reader, int) {
	t.Helper()
	executable, err := os.Executable()
	require.NoError(t, err)
	t.Setenv("DAGGER_TEST_DIALSTDIO_CHILD", "1")
	t.Setenv("DAGGER_TEST_DIALSTDIO_ADDR", "unix://"+path)
	t.Setenv("DAGGER_TEST_DIALSTDIO_TIMEOUT", strconv.Itoa(seconds))
	// The child's race detector should still report errors, but not add its
	// default one-second exit sleep to the timeout/lifecycle assertions.
	t.Setenv("GORACE", os.Getenv("GORACE")+" atexit_sleep_ms=0")
	conn, err := commandconn.New(ctx, executable, "-test.run=^TestDialStdioProcess$")
	require.NoError(t, err)
	t.Cleanup(func() { conn.Close() })
	reader := bufio.NewReader(conn)
	type ready struct {
		line string
		err  error
	}
	done := make(chan ready, 1)
	go func() {
		line, err := reader.ReadString('\n')
		done <- ready{line, err}
	}()
	select {
	case result := <-done:
		require.NoError(t, result.err)
		pid, err := strconv.Atoi(strings.TrimSpace(result.line))
		require.NoError(t, err)
		require.Greater(t, pid, 0)
		return conn, reader, pid
	case <-time.After(2 * time.Second):
		t.Fatal("helper did not start")
		return nil, nil, 0
	}
}

func readStdioToEOF(t *testing.T, reader io.Reader) string {
	t.Helper()
	type result struct {
		data []byte
		err  error
	}
	done := make(chan result, 1)
	go func() {
		data, err := io.ReadAll(reader)
		done <- result{data, err}
	}()
	select {
	case got := <-done:
		require.NoError(t, got.err)
		return string(got.data)
	case <-time.After(2 * time.Second):
		t.Fatal("stdio did not reach EOF")
		return ""
	}
}
