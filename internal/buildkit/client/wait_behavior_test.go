package client

import (
	"context"
	"errors"
	"net"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	controlapi "github.com/dagger/dagger/internal/buildkit/api/services/control"
	"github.com/dagger/dagger/internal/buildkit/util/grpcerrors"
	"google.golang.org/grpc"
	"google.golang.org/grpc/backoff"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

type waitBehaviorServer struct {
	controlapi.UnimplementedControlServer
	info func(context.Context) (*controlapi.InfoResponse, error)
}

func (s *waitBehaviorServer) Info(ctx context.Context, _ *controlapi.InfoRequest) (*controlapi.InfoResponse, error) {
	return s.info(ctx)
}

func newWaitBehaviorClient(t *testing.T, info func(context.Context) (*controlapi.InfoResponse, error), opts ...ClientOpt) *Client {
	t.Helper()
	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	controlapi.RegisterControlServer(server, &waitBehaviorServer{info: info})
	go server.Serve(listener)
	t.Cleanup(server.Stop)
	t.Cleanup(func() { _ = listener.Close() })
	opts = append(opts, WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
		return listener.DialContext(ctx)
	}))
	// Use New, including the production grpcerrors client interceptor.
	client, err := New(t.Context(), "passthrough:///wait-behavior", opts...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func waitSignal(t *testing.T, signal <-chan struct{}) {
	t.Helper()
	select {
	case <-signal:
	case <-time.After(5 * time.Second):
		t.Fatal("did not reach the requested readiness boundary")
	}
}

func waitResult(t *testing.T, result <-chan error) error {
	t.Helper()
	select {
	case err := <-result:
		return err
	case <-time.After(2 * time.Second):
		t.Fatal("readiness did not finish promptly")
		return nil
	}
}

func TestWaitQueuedContextCause(t *testing.T) {
	for _, deadline := range []bool{false, true} {
		name := "cancel"
		if deadline {
			name = "deadline"
		}
		t.Run(name, func(t *testing.T) {
			attempted, started := make(chan struct{}), make(chan struct{})
			var attemptOnce, startOnce sync.Once
			client, err := New(t.Context(), "passthrough:///queued-readiness",
				WithContextDialer(func(context.Context, string) (net.Conn, error) {
					attemptOnce.Do(func() { close(attempted) })
					return nil, errors.New("transport unavailable")
				}),
				WithGRPCDialOption(grpc.WithConnectParams(grpc.ConnectParams{
					// Test-only long backoff keeps the transport unavailable. The
					// production retry policy is not changed by this fixture.
					Backoff: backoff.Config{BaseDelay: time.Minute, MaxDelay: time.Minute, Multiplier: 1},
				})),
				WithGRPCDialOption(grpc.WithChainUnaryInterceptor(func(ctx context.Context, method string, req, reply any, conn *grpc.ClientConn, invoke grpc.UnaryInvoker, opts ...grpc.CallOption) error {
					startOnce.Do(func() { close(started) })
					return invoke(ctx, method, req, reply, conn, opts...)
				})))
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { _ = client.Close() })
			cause := errors.New("readiness stopped by caller")
			var ctx context.Context
			var cancel context.CancelFunc
			if deadline {
				ctx, cancel = context.WithTimeoutCause(t.Context(), 500*time.Millisecond, cause)
			} else {
				var cancelCause context.CancelCauseFunc
				ctx, cancelCause = context.WithCancelCause(t.Context())
				cancel = func() { cancelCause(cause) }
			}
			defer cancel()
			done := make(chan error, 1)
			go func() { done <- client.Wait(ctx) }()
			waitSignal(t, attempted)
			waitSignal(t, started)
			if !deadline {
				cancel()
			}
			if err := waitResult(t, done); !errors.Is(err, cause) {
				t.Fatalf("lost local %s cause: %v", name, err)
			}
		})
	}
}

func TestWaitPreCanceledCause(t *testing.T) {
	for _, custom := range []bool{false, true} {
		name := "plain"
		if custom {
			name = "custom"
		}
		t.Run(name, func(t *testing.T) {
			client := newWaitBehaviorClient(t, func(context.Context) (*controlapi.InfoResponse, error) {
				return &controlapi.InfoResponse{}, nil
			})
			cause := error(context.Canceled)
			if custom {
				cause = errors.New("custom pre-cancellation")
			}
			ctx, cancel := context.WithCancelCause(t.Context())
			cancel(cause)
			if err := client.Wait(ctx); !errors.Is(err, cause) {
				t.Fatalf("lost pre-cancellation cause: %v", err)
			}
		})
	}
}

func TestWaitServerCancellationStatus(t *testing.T) {
	for _, code := range []codes.Code{codes.Canceled, codes.DeadlineExceeded} {
		t.Run(code.String(), func(t *testing.T) {
			var calls atomic.Int32
			client := newWaitBehaviorClient(t, func(context.Context) (*controlapi.InfoResponse, error) {
				calls.Add(1)
				return nil, status.Error(code, "server response, not local cancellation")
			})
			ctx, cancel := context.WithTimeout(t.Context(), 5*time.Second)
			defer cancel()
			err := client.Wait(ctx)
			if ctx.Err() != nil || grpcerrors.Code(err) != code || calls.Load() != 1 {
				t.Fatalf("server status changed or retried: err=%v ctx=%v calls=%d", err, ctx.Err(), calls.Load())
			}
		})
	}
}

func TestWaitApplicationUnavailableRetry(t *testing.T) {
	var calls atomic.Int32
	times := make(chan time.Time, 2)
	client := newWaitBehaviorClient(t, func(context.Context) (*controlapi.InfoResponse, error) {
		times <- time.Now()
		if calls.Add(1) == 1 {
			return nil, status.Error(codes.Unavailable, "server still initializing")
		}
		return &controlapi.InfoResponse{}, nil
	})
	ctx, cancel := context.WithTimeout(t.Context(), 5*time.Second)
	defer cancel()
	if err := client.Wait(ctx); err != nil {
		t.Fatal(err)
	}
	if calls.Load() != 2 {
		t.Fatalf("expected one server retry, got %d calls", calls.Load())
	}
	first, second := <-times, <-times
	if elapsed := second.Sub(first); elapsed < 900*time.Millisecond {
		t.Fatalf("server retry policy was shortened: %s", elapsed)
	}
}

func TestWaitApplicationUnavailableCancellation(t *testing.T) {
	returned := make(chan struct{})
	var calls atomic.Int32
	var once sync.Once
	client := newWaitBehaviorClient(t, func(context.Context) (*controlapi.InfoResponse, error) {
		calls.Add(1)
		return nil, status.Error(codes.Unavailable, "server still initializing")
	}, WithGRPCDialOption(grpc.WithChainUnaryInterceptor(func(ctx context.Context, method string, req, reply any, conn *grpc.ClientConn, invoke grpc.UnaryInvoker, opts ...grpc.CallOption) error {
		err := invoke(ctx, method, req, reply, conn, opts...)
		if grpcerrors.Code(err) == codes.Unavailable {
			once.Do(func() { close(returned) })
		}
		return err
	})))
	cause := errors.New("cancel during server retry")
	ctx, cancel := context.WithCancelCause(t.Context())
	defer cancel(cause)
	done := make(chan error, 1)
	go func() { done <- client.Wait(ctx) }()
	waitSignal(t, returned)
	cancel(cause)
	if err := waitResult(t, done); !errors.Is(err, cause) || calls.Load() != 1 {
		t.Fatalf("lost retry cancellation or retried: err=%v calls=%d", err, calls.Load())
	}
}
