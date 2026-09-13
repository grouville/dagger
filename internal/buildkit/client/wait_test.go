package client

import (
	"context"
	"errors"
	"net"
	"sync/atomic"
	"testing"
	"time"

	controlapi "github.com/dagger/dagger/internal/buildkit/api/services/control"
	"google.golang.org/grpc"
	"google.golang.org/grpc/backoff"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

type readinessServer struct {
	controlapi.UnimplementedControlServer
	code codes.Code
}

func (s readinessServer) Info(context.Context, *controlapi.InfoRequest) (*controlapi.InfoResponse, error) {
	if s.code != codes.OK {
		return nil, status.Error(s.code, "readiness test")
	}
	return &controlapi.InfoResponse{}, nil
}

func TestWaitTransportReadiness(t *testing.T) {
	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	controlapi.RegisterControlServer(server, &readinessServer{})
	go server.Serve(listener)
	t.Cleanup(server.Stop)
	t.Cleanup(func() { listener.Close() })
	var attempts atomic.Int32
	conn, err := grpc.NewClient("passthrough:///readiness",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithConnectParams(grpc.ConnectParams{Backoff: backoff.Config{
			BaseDelay: 10 * time.Millisecond, Multiplier: 1, MaxDelay: 10 * time.Millisecond,
		}, MinConnectTimeout: time.Second}),
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			if attempts.Add(1) == 1 {
				return nil, errors.New("engine starting")
			}
			return listener.DialContext(ctx)
		}))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.Close() })
	// A transport that becomes ready after 10ms must not wait for the old
	// one-second polling timer. The generous deadline avoids a tight timing test.
	ctx, cancel := context.WithTimeout(context.Background(), 750*time.Millisecond)
	defer cancel()
	if err := (&Client{conn: conn}).Wait(ctx); err != nil {
		t.Fatal(err)
	}
	if attempts.Load() < 2 {
		t.Fatal("did not exercise transient connection failure")
	}
}

func TestWaitCancellation(t *testing.T) {
	conn, err := grpc.NewClient("passthrough:///unavailable",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) {
			return nil, errors.New("unavailable")
		}))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := (&Client{conn: conn}).Wait(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected cancellation, got %v", err)
	}
}

func TestWaitServerStatus(t *testing.T) {
	for _, code := range []codes.Code{codes.OK, codes.Unimplemented, codes.PermissionDenied, codes.Unavailable} {
		t.Run(code.String(), func(t *testing.T) {
			listener := bufconn.Listen(1024 * 1024)
			server := grpc.NewServer()
			controlapi.RegisterControlServer(server, &readinessServer{code: code})
			go server.Serve(listener)
			t.Cleanup(server.Stop)
			t.Cleanup(func() { listener.Close() })
			conn, err := grpc.NewClient("passthrough:///status",
				grpc.WithTransportCredentials(insecure.NewCredentials()),
				grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
					return listener.DialContext(ctx)
				}))
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { conn.Close() })
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			defer cancel()
			err = (&Client{conn: conn}).Wait(ctx)
			switch code {
			case codes.OK, codes.Unimplemented:
				if err != nil {
					t.Fatal(err)
				}
			case codes.Unavailable:
				if !errors.Is(err, context.DeadlineExceeded) {
					t.Fatalf("expected retry until deadline, got %v", err)
				}
			default:
				if status.Code(err) != code {
					t.Fatalf("expected %v, got %v", code, err)
				}
			}
		})
	}
}
