package core

import (
	"context"
	"errors"
	"io/fs"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	fstypes "github.com/dagger/dagger/internal/fsutil/types"
)

type hostTreeReaderStub struct {
	read  func(context.Context, string) ([]byte, error)
	stat  func(context.Context, string, bool) (*fstypes.Stat, error)
	reads int
	stats int
}

func (c *hostTreeReaderStub) ReadCallerHostFile(ctx context.Context, path string) ([]byte, error) {
	c.reads++
	return c.read(ctx, path)
}

func (c *hostTreeReaderStub) StatCallerHostPath(ctx context.Context, path string, absolute bool) (*fstypes.Stat, error) {
	c.stats++
	return c.stat(ctx, path, absolute)
}

func TestHostTreeFileReaderReadsCurrentContents(t *testing.T) {
	key := struct{}{}
	ctx := context.WithValue(t.Context(), key, "caller")
	root := t.TempDir()
	contents := "first"
	client := &hostTreeReaderStub{read: func(gotCtx context.Context, path string) ([]byte, error) {
		require.Equal(t, "caller", gotCtx.Value(key))
		require.Equal(t, filepath.Join(root, "nested", "dagger.toml"), path)
		return []byte(contents), nil
	}, stat: func(context.Context, string, bool) (*fstypes.Stat, error) {
		t.Fatal("successful reads must not issue a redundant stat request")
		return nil, nil
	}}
	read := hostTreeFileReader(ctx, root, client)
	for _, want := range []string{"first", "second", ""} {
		contents = want
		data, found, err := read("nested/dagger.toml")
		require.NoError(t, err)
		require.True(t, found)
		require.Equal(t, want, string(data))
	}
	require.Equal(t, 3, client.reads)
	require.Zero(t, client.stats)
}

func TestHostTreeFileReaderFailures(t *testing.T) {
	readErr := errors.New("read denied")
	statErr := errors.New("stat denied")
	notFound := status.Error(codes.NotFound, "missing")
	for _, tc := range []struct {
		name      string
		readErr   error
		stat      *fstypes.Stat
		statErr   error
		wantErr   error
		wantStats int
	}{
		{name: "missing", readErr: notFound},
		{name: "directory", readErr: readErr, stat: &fstypes.Stat{Mode: uint32(fs.ModeDir)}, wantStats: 1},
		{name: "read failure", readErr: readErr, stat: &fstypes.Stat{}, wantErr: readErr, wantStats: 1},
		{name: "stat failure", readErr: readErr, statErr: statErr, wantErr: statErr, wantStats: 1},
		{name: "removed before fallback", readErr: readErr, statErr: notFound, wantStats: 1},
		{name: "cancelled", readErr: context.Canceled, statErr: context.Canceled, wantErr: context.Canceled, wantStats: 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			client := &hostTreeReaderStub{read: func(context.Context, string) ([]byte, error) {
				return nil, tc.readErr
			}, stat: func(_ context.Context, _ string, absolute bool) (*fstypes.Stat, error) {
				require.False(t, absolute)
				return tc.stat, tc.statErr
			}}
			data, found, err := hostTreeFileReader(t.Context(), t.TempDir(), client)("dagger.toml")
			if tc.wantErr == nil {
				require.NoError(t, err)
			} else {
				require.ErrorIs(t, err, tc.wantErr)
			}
			require.Nil(t, data)
			require.False(t, found)
			require.Equal(t, tc.wantStats, client.stats)
		})
	}
}
