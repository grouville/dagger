package main

import (
	"context"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestDialerWaitsForStartingSocket(t *testing.T) {
	path := filepath.Join(t.TempDir(), "engine.sock")
	type result struct {
		conn net.Conn
		err  error
	}
	done := make(chan result, 1)
	go func() {
		conn, err := dialer("unix://"+path, time.Second)
		done <- result{conn: conn, err: err}
	}()

	// A fresh engine may not have bound its socket when docker exec starts
	// the helper. The existing connection timeout should cover that startup
	// interval rather than immediately failing into the parent's backoff.
	select {
	case got := <-done:
		if got.conn != nil {
			got.conn.Close()
		}
		t.Fatalf("dial returned before the engine socket was started: %v", got.err)
	case <-time.After(30 * time.Millisecond):
	}
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	select {
	case got := <-done:
		if got.err != nil {
			t.Fatal(got.err)
		}
		got.conn.Close()
	case <-time.After(750 * time.Millisecond):
		t.Fatal("dial did not observe the engine socket becoming ready")
	}
}

func TestDialerWaitsForStaleSocket(t *testing.T) {
	path := filepath.Join(t.TempDir(), "engine.sock")
	old, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	old.SetUnlinkOnClose(false)
	old.Close()
	// Establish the retryable refusal rather than a missing-path fixture.
	_, err = net.Dial("unix", path)
	if !errors.Is(err, syscall.ECONNREFUSED) {
		t.Fatalf("expected stale socket refusal, got %v", err)
	}
	done := make(chan error, 1)
	go func() {
		conn, err := dialer("unix://"+path, time.Second)
		if conn != nil {
			conn.Close()
		}
		done <- err
	}()
	select {
	case err := <-done:
		t.Fatalf("dial returned before the stale socket was replaced: %v", err)
	case <-time.After(30 * time.Millisecond):
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(750 * time.Millisecond):
		t.Fatal("dial did not observe replacement listener")
	}
}

func TestDialerMissingSocketTimeout(t *testing.T) {
	path := filepath.Join(t.TempDir(), "engine.sock")
	started := time.Now()
	conn, err := dialer("unix://"+path, 60*time.Millisecond)
	if conn != nil {
		conn.Close()
		t.Fatal("unexpected connection")
	}
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected total readiness deadline, got %v", err)
	}
	if !strings.Contains(err.Error(), path) || !strings.Contains(err.Error(), "last dial error") {
		t.Fatalf("timeout lost socket/last-error diagnostics: %v", err)
	}
	if elapsed := time.Since(started); elapsed < 60*time.Millisecond || elapsed > 500*time.Millisecond {
		t.Fatalf("unexpected readiness timeout duration: %s", elapsed)
	}
}

func TestDialerNonTransientAndNonPositiveTimeouts(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "not-a-directory")
	if err := os.WriteFile(file, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name, address string
		timeout       time.Duration
		wantErr       error
	}{
		{"malformed", "not-an-address", time.Second, nil},
		{"wrong-protocol", "tcp://127.0.0.1:1", time.Second, nil},
		{"not-directory", "unix://" + filepath.Join(file, "engine.sock"), time.Second, syscall.ENOTDIR},
		{"zero-missing", "unix://" + filepath.Join(dir, "absent.sock"), 0, syscall.ENOENT},
		{"negative-missing", "unix://" + filepath.Join(dir, "absent.sock"), -time.Second, nil},
	} {
		t.Run(test.name, func(t *testing.T) {
			started := time.Now()
			conn, err := dialer(test.address, test.timeout)
			if conn != nil {
				conn.Close()
			}
			if err == nil || (test.wantErr != nil && !errors.Is(err, test.wantErr)) {
				t.Fatalf("unexpected error: %v, want %v", err, test.wantErr)
			}
			if test.timeout < 0 {
				var timeoutErr net.Error
				if !errors.As(err, &timeoutErr) || !timeoutErr.Timeout() {
					t.Fatalf("negative DialTimeout lost its timeout behavior: %v", err)
				}
			}
			if elapsed := time.Since(started); elapsed > 500*time.Millisecond {
				t.Fatalf("non-retry case waited: %s", elapsed)
			}
		})
	}
}

func TestDialerReadyConnectionOutlivesDialDeadline(t *testing.T) {
	path := filepath.Join(t.TempDir(), "engine.sock")
	listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: path, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	conn, err := dialer("unix://"+path, 30*time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.Close() })
	peer, err := listener.AcceptUnix()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { peer.Close() })
	// The readiness deadline belongs only to dialing. The unchanged copy
	// path still needs a working Unix half-close after that deadline expires.
	time.Sleep(50 * time.Millisecond)
	if err := conn.(*net.UnixConn).CloseWrite(); err != nil {
		t.Fatal(err)
	}
	if err := peer.SetDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	data, err := io.ReadAll(peer)
	if err != nil || len(data) != 0 {
		t.Fatalf("peer did not observe half-close: %q, %v", data, err)
	}
	if _, err := peer.Write([]byte("ok")); err != nil {
		t.Fatal(err)
	}
	if err := peer.CloseWrite(); err != nil {
		t.Fatal(err)
	}
	if err := conn.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	data, err = io.ReadAll(conn)
	if err != nil || string(data) != "ok" {
		t.Fatalf("connection changed after dial deadline: %q, %v", data, err)
	}
}
