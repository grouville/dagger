package engineutil

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/dagger/dagger/engine"
	engineclient "github.com/dagger/dagger/engine/client"
	"github.com/dagger/dagger/internal/buildkit/session/filesync"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

type statReadSource struct {
	engineclient.FilesyncSource
	legacy   bool
	mu       sync.Mutex
	requests []engine.LocalImportOpts
}

type statReadStream struct {
	filesync.FileSync_DiffCopyServer
	ctx context.Context
}

func (s statReadStream) Context() context.Context { return s.ctx }

func (s *statReadSource) DiffCopy(stream filesync.FileSync_DiffCopyServer) error {
	opts, err := engine.LocalImportOptsFromContext(stream.Context())
	if err != nil {
		return err
	}
	s.mu.Lock()
	s.requests = append(s.requests, *opts)
	s.mu.Unlock()
	if opts.StatPathOnly && filepath.Base(opts.Path) == "stat-error.toml" {
		return status.Error(codes.PermissionDenied, "fixture metadata failure")
	}
	if s.legacy && opts.StatPathOnly {
		// The original handler gives StatPathOnly precedence and ends the
		// stream after the stat, even when ReadSingleFileOnly was requested.
		opts.ReadSingleFileOnly = false
		ctx := metadata.NewIncomingContext(stream.Context(), opts.ToGRPCMD())
		stream = statReadStream{FileSync_DiffCopyServer: stream, ctx: ctx}
	}
	return s.FilesyncSource.DiffCopy(stream)
}

func (s *statReadSource) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.requests)
}

type statReadCaller struct{ conn *grpc.ClientConn }

func (c statReadCaller) Conn() *grpc.ClientConn { return c.conn }
func (statReadCaller) Supports(string) bool     { return true }

func newStatReadClient(t testing.TB, legacy bool) (*Client, context.Context, *statReadSource) {
	t.Helper()
	listener := bufconn.Listen(1 << 20)
	server := grpc.NewServer()
	local, err := engineclient.NewFilesyncer()
	require.NoError(t, err)
	source := &statReadSource{FilesyncSource: local.AsSource(), legacy: legacy}
	filesync.RegisterFileSyncServer(server, source)
	go func() { _ = server.Serve(listener) }()
	conn, err := grpc.NewClient("passthrough:///stat-read", grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }))
	require.NoError(t, err)
	t.Cleanup(func() { _ = conn.Close(); server.Stop(); _ = listener.Close() })
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "stat-read"})
	client := &Client{Opts: &Opts{GetClientCaller: func(context.Context, string) (SessionCaller, error) { return statReadCaller{conn}, nil }}, closeCtx: ctx}
	return client, ctx, source
}

func TestCallerHostStatAndRead(t *testing.T) {
	for _, legacy := range []bool{false, true} {
		name := "current source"
		if legacy {
			name = "legacy source"
		}
		t.Run(name, func(t *testing.T) {
			client, ctx, source := newStatReadClient(t, legacy)
			root := t.TempDir()
			regular := filepath.Join(root, "dagger.toml")
			empty := filepath.Join(root, "empty.toml")
			require.NoError(t, os.WriteFile(regular, []byte("configuration"), 0o600))
			require.NoError(t, os.WriteFile(empty, nil, 0o600))
			require.NoError(t, os.WriteFile(filepath.Join(root, "stat-error.toml"), []byte("readable"), 0o600))
			require.NoError(t, os.WriteFile(filepath.Join(root, "unreadable.toml"), []byte("hidden"), 0))
			for name, target := range map[string]string{"file-link": regular, "directory-link": root, "broken-link": filepath.Join(root, "absent")} {
				require.NoError(t, os.Symlink(target, filepath.Join(root, name)))
			}
			for _, test := range []struct {
				name, path, data string
				haveStat, isDir  bool
				code             codes.Code
				requests         int
			}{
				{"regular", regular, "configuration", true, false, codes.OK, 1},
				{"empty", empty, "", true, false, codes.OK, 1},
				{"missing", filepath.Join(root, "absent"), "", false, false, codes.NotFound, 1},
				{"directory", root, "", true, true, codes.OK, 1},
				{"file link", filepath.Join(root, "file-link"), "configuration", true, false, codes.OK, 1},
				{"directory link", filepath.Join(root, "directory-link"), "", true, false, codes.Unknown, 1},
				{"broken link", filepath.Join(root, "broken-link"), "", true, false, codes.NotFound, 1},
				{"metadata failure", filepath.Join(root, "stat-error.toml"), "", false, false, codes.PermissionDenied, 1},
				{"unreadable", filepath.Join(root, "unreadable.toml"), "", true, false, codes.Unknown, 1},
			} {
				t.Run(test.name, func(t *testing.T) {
					if test.name == "unreadable" && os.Geteuid() == 0 {
						t.Skip("root can read permission fixture")
					}
					before := source.count()
					data, stat, err := client.ReadCallerHostFileWithStat(ctx, test.path)
					require.Equal(t, test.code, status.Code(err), "%v", err)
					require.Equal(t, test.haveStat, stat != nil)
					if stat != nil {
						require.Equal(t, test.isDir, stat.IsDir())
					}
					require.Equal(t, test.data, string(data))
					want := test.requests
					if legacy && test.haveStat && !test.isDir {
						want++
					}
					require.Equal(t, want, source.count()-before)
				})
			}
			require.NoError(t, os.WriteFile(regular, []byte("edited"), 0o600))
			data, _, err := client.ReadCallerHostFileWithStat(ctx, regular)
			require.NoError(t, err)
			require.Equal(t, "edited", string(data))
			// Existing engine requests still receive exactly one response each.
			_, err = client.StatCallerHostPath(ctx, regular, false)
			require.NoError(t, err)
			data, err = client.ReadCallerHostFile(ctx, regular)
			require.NoError(t, err)
			require.Equal(t, "edited", string(data))
		})
	}
}

func TestCallerHostStatAndReadSizeLimit(t *testing.T) {
	client, ctx, _ := newStatReadClient(t, false)
	path := filepath.Join(t.TempDir(), "large.toml")
	require.NoError(t, os.WriteFile(path, make([]byte, MaxFileContentsChunkSize+1), 0o600))
	data, stat, err := client.ReadCallerHostFileWithStat(ctx, path)
	require.Empty(t, data)
	require.NotNil(t, stat)
	require.ErrorContains(t, err, "file contents too large")
	_, err = client.ReadCallerHostFile(ctx, path)
	require.ErrorContains(t, err, "file contents too large")
}

func TestCallerHostStatAndReadCancellation(t *testing.T) {
	client, ctx, _ := newStatReadClient(t, false)
	ctx, cancel := context.WithCancel(ctx)
	cancel()
	_, stat, err := client.ReadCallerHostFileWithStat(ctx, "unused")
	require.Nil(t, stat)
	require.Equal(t, codes.Canceled, status.Code(err))
}
