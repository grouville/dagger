package core

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/engine"
	engineclient "github.com/dagger/dagger/engine/client"
	"github.com/dagger/dagger/internal/buildkit/session/filesync"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

type moduleHostFileRPCClient struct {
	filesync.FileSyncClient
	reads, stats atomic.Int64
}

func newModuleHostFileRPCClient(t testing.TB) *moduleHostFileRPCClient {
	t.Helper()
	listener := bufconn.Listen(1 << 20)
	server := grpc.NewServer()
	local, err := engineclient.NewFilesyncer()
	require.NoError(t, err)
	local.AsSource().Register(server)
	go func() { _ = server.Serve(listener) }()
	conn, err := grpc.NewClient("passthrough:///host-file-test",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }))
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = conn.Close()
		server.Stop()
		_ = listener.Close()
	})
	return &moduleHostFileRPCClient{FileSyncClient: filesync.NewFileSyncClient(conn)}
}

func (c *moduleHostFileRPCClient) receive(ctx context.Context, opts engine.LocalImportOpts, result any) error {
	stream, err := c.DiffCopy(opts.AppendToOutgoingContext(ctx))
	if err != nil {
		return err
	}
	defer stream.CloseSend()
	if err := stream.RecvMsg(result); err != nil {
		return fmt.Errorf("receive host file response: %w", err)
	}
	return nil
}

func (c *moduleHostFileRPCClient) ReadCallerHostFile(ctx context.Context, path string) ([]byte, error) {
	c.reads.Add(1)
	var message filesync.BytesMessage
	err := c.receive(ctx, engine.LocalImportOpts{Path: path, ReadSingleFileOnly: true, MaxFileSize: 4096}, &message)
	return message.Data, err
}

func (c *moduleHostFileRPCClient) StatCallerHostPath(ctx context.Context, path string, returnAbs bool) (*fstypes.Stat, error) {
	c.stats.Add(1)
	var message fstypes.Stat
	err := c.receive(ctx, engine.LocalImportOpts{Path: path, StatPathOnly: true, StatReturnAbsPath: returnAbs}, &message)
	return &message, err
}

func TestModuleHostFileReaderBehavior(t *testing.T) {
	client := newModuleHostFileRPCClient(t)
	root := t.TempDir()
	regular := filepath.Join(root, "regular.toml")
	require.NoError(t, os.WriteFile(regular, []byte("configuration"), 0o600))
	empty := filepath.Join(root, "empty.toml")
	require.NoError(t, os.WriteFile(empty, nil, 0o600))
	oversized := filepath.Join(root, "large.toml")
	require.NoError(t, os.WriteFile(oversized, make([]byte, 4097), 0o600))
	unreadable := filepath.Join(root, "unreadable.toml")
	require.NoError(t, os.WriteFile(unreadable, []byte("hidden"), 0))
	for name, target := range map[string]string{"file-link": regular, "directory-link": root, "broken-link": filepath.Join(root, "absent")} {
		require.NoError(t, os.Symlink(target, filepath.Join(root, name)))
	}
	for _, test := range []struct {
		name, path string
		found      bool
		data       string
		code       codes.Code
	}{
		{"regular", regular, true, "configuration", codes.OK},
		{"empty", empty, true, "", codes.OK},
		{"missing", filepath.Join(root, "missing"), false, "", codes.OK},
		{"directory", root, false, "", codes.OK},
		{"file link", filepath.Join(root, "file-link"), true, "configuration", codes.OK},
		{"directory link", filepath.Join(root, "directory-link"), false, "", codes.Unknown},
		{"broken link", filepath.Join(root, "broken-link"), false, "", codes.NotFound},
		{"oversized", oversized, false, "", codes.Unknown},
		{"unreadable", unreadable, false, "", codes.Unknown},
	} {
		t.Run(test.name, func(t *testing.T) {
			if test.path == unreadable && os.Geteuid() == 0 {
				t.Skip("root can read the permission fixture")
			}
			data, found, err := readModuleHostFile(t.Context(), client, test.path)
			require.Equal(t, test.found, found)
			require.Equal(t, test.data, string(data))
			require.Equal(t, test.code, status.Code(err), "%v", err)
		})
	}
	// Current bytes remain observable through the same reader and connection.
	require.NoError(t, os.WriteFile(regular, []byte("edited"), 0o600))
	data, found, err := readModuleHostFile(t.Context(), client, regular)
	require.NoError(t, err)
	require.True(t, found)
	require.Equal(t, "edited", string(data))
}

func TestModuleHostFileReaderOneRequest(t *testing.T) {
	client := newModuleHostFileRPCClient(t)
	file := filepath.Join(t.TempDir(), "dagger.toml")
	require.NoError(t, os.WriteFile(file, []byte("current configuration"), 0o600))
	data, found, err := readModuleHostFile(t.Context(), client, file)
	require.NoError(t, err)
	require.True(t, found)
	require.Equal(t, "current configuration", string(data))
	require.EqualValues(t, 1, client.reads.Load())
	require.Zero(t, client.stats.Load(), "a successful read needs no separate stat request")
}

func BenchmarkModuleHostFileReader(b *testing.B) {
	client := newModuleHostFileRPCClient(b)
	root := b.TempDir()
	file := filepath.Join(root, "dagger.toml")
	require.NoError(b, os.WriteFile(file, []byte("current configuration"), 0o600))
	for _, scenario := range []struct {
		name, path string
		found      bool
		data       string
	}{
		{"regular", file, true, "current configuration"},
		{"missing", filepath.Join(root, "missing.toml"), false, ""},
		{"directory", root, false, ""},
	} {
		b.Run(scenario.name, func(b *testing.B) {
			ctx := b.Context()
			check := func() {
				data, found, err := readModuleHostFile(ctx, client, scenario.path)
				if err != nil || found != scenario.found || string(data) != scenario.data {
					b.Fatalf("data=%q, found=%v, err=%v", data, found, err)
				}
			}
			check()
			client.reads.Store(0)
			client.stats.Store(0)
			b.ReportAllocs()
			b.ResetTimer()
			for range b.N {
				check()
			}
			b.StopTimer()
			b.ReportMetric(float64(client.reads.Load()+client.stats.Load())/float64(b.N), "requests/op")
		})
	}
}
