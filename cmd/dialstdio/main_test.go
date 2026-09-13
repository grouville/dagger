package main

import (
	"context"
	"io"
	"net"
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestDialerWaitsForUnixSocket(t *testing.T) {
	for _, stale := range []bool{false, true} {
		name := "missing"
		if stale {
			name = "refused"
		}
		t.Run(name, func(t *testing.T) {
			path := unixSocketPath(t)
			if stale {
				listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
				require.NoError(t, err)
				listener.SetUnlinkOnClose(false)
				require.NoError(t, listener.Close())
				info, err := os.Stat(path)
				require.NoError(t, err)
				require.NotZero(t, info.Mode()&os.ModeSocket)
			}
			future := startUnixListenerAfter(t, path, stale, 40*time.Millisecond)
			conn, err := dialer("unix://"+path, 750*time.Millisecond)
			require.NoError(t, err, "positive connection timeout should allow a briefly unavailable engine socket")
			t.Cleanup(func() { conn.Close() })
			<-future.done
			require.NoError(t, future.err)
			require.NotNil(t, future.listener)
			require.NoError(t, future.listener.(*net.UnixListener).SetDeadline(time.Now().Add(time.Second)))
			accepted, err := future.listener.Accept()
			require.NoError(t, err)
			t.Cleanup(func() { accepted.Close() })
		})
	}
}

func TestDialerTimeoutBudget(t *testing.T) {
	for _, stale := range []bool{false, true} {
		name := "missing"
		if stale {
			name = "refused"
		}
		t.Run(name, func(t *testing.T) {
			path := unixSocketPath(t)
			if stale {
				listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
				require.NoError(t, err)
				listener.SetUnlinkOnClose(false)
				require.NoError(t, listener.Close())
			}
			const budget = 60 * time.Millisecond
			started := time.Now()
			conn, err := dialer("unix://"+path, budget)
			elapsed := time.Since(started)
			require.Nil(t, conn)
			require.Error(t, err)
			var netErr net.Error
			require.ErrorAs(t, err, &netErr)
			require.True(t, netErr.Timeout())
			require.True(t, os.IsTimeout(err))
			require.ErrorIs(t, err, context.DeadlineExceeded)
			require.Contains(t, err.Error(), path)
			require.GreaterOrEqual(t, elapsed, budget)
			require.Less(t, elapsed, 350*time.Millisecond, "retries must share one absolute deadline")
		})
	}
}

func TestDialerNonpositiveTimeout(t *testing.T) {
	path := unixSocketPath(t)
	for _, timeout := range []time.Duration{0, -time.Second} {
		conn, expected := net.DialTimeout("unix", path, timeout)
		require.Nil(t, conn)
		started := time.Now()
		conn, actual := dialer("unix://"+path, timeout)
		require.Nil(t, conn)
		require.EqualError(t, actual, expected.Error())
		require.Equal(t, os.IsTimeout(expected), os.IsTimeout(actual))
		require.Less(t, time.Since(started), 250*time.Millisecond)
	}
	listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
	require.NoError(t, err)
	t.Cleanup(func() { listener.Close() })
	conn, err := dialer("unix://"+path, 0)
	require.NoError(t, err)
	conn.Close()
}

func TestDialerPermanentErrors(t *testing.T) {
	file := unixSocketPath(t)
	require.NoError(t, os.WriteFile(file, nil, 0600))
	for _, address := range []string{"no-scheme", "tcp://localhost:1234", "unix://", "unix://" + filepath.Join(file, "s")} {
		started := time.Now()
		conn, err := dialer(address, 2*time.Second)
		require.Nil(t, conn)
		require.Error(t, err)
		require.Less(t, time.Since(started), 250*time.Millisecond, address)
		if address == "unix://"+filepath.Join(file, "s") {
			require.ErrorIs(t, err, syscall.ENOTDIR)
		}
	}
}

func TestDialerDeadlineDoesNotLimitEstablishedStream(t *testing.T) {
	path := unixSocketPath(t)
	listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
	require.NoError(t, err)
	t.Cleanup(func() { listener.Close() })
	conn, err := dialer("unix://"+path, 50*time.Millisecond)
	require.NoError(t, err)
	t.Cleanup(func() { conn.Close() })
	require.NoError(t, listener.SetDeadline(time.Now().Add(time.Second)))
	accepted, err := listener.AcceptUnix()
	require.NoError(t, err)
	t.Cleanup(func() { accepted.Close() })
	// Let the connection deadline expire before transferring anything. Do not
	// overwrite the client deadline: that would hide a leaked dial deadline.
	time.Sleep(80 * time.Millisecond)
	require.NoError(t, accepted.SetDeadline(time.Now().Add(time.Second)))
	_, err = accepted.Write([]byte("after deadline"))
	require.NoError(t, err)
	got := make([]byte, len("after deadline"))
	done := make(chan error, 1)
	go func() {
		_, err := io.ReadFull(conn, got)
		done <- err
	}()
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(time.Second):
		t.Fatal("established stream did not transfer data after its dial deadline")
	}
	require.Equal(t, "after deadline", string(got))
}

type unixListenerFuture struct {
	done     chan struct{}
	listener net.Listener
	err      error
}

func unixSocketPath(t *testing.T) string {
	t.Helper()
	// A full test name in t.TempDir can exceed Unix socket address limits on
	// platforms with a longer temporary-directory prefix, notably macOS.
	dir, err := os.MkdirTemp("", "ds-")
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, os.RemoveAll(dir)) })
	return filepath.Join(dir, "s")
}

func startUnixListenerAfter(t *testing.T, path string, replaceStale bool, delay time.Duration) *unixListenerFuture {
	t.Helper()
	ctx, cancel := context.WithCancel(t.Context())
	future := &unixListenerFuture{done: make(chan struct{})}
	t.Cleanup(func() {
		cancel()
		<-future.done
		if future.listener != nil {
			future.listener.Close()
		}
	})
	go func() {
		defer close(future.done)
		timer := time.NewTimer(delay)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			future.err = ctx.Err()
			return
		case <-timer.C:
		}
		if replaceStale {
			// Only the stale socket created by this test in its own TempDir.
			if future.err = os.Remove(path); future.err != nil {
				return
			}
		}
		future.listener, future.err = net.Listen("unix", path)
	}()
	return future
}
