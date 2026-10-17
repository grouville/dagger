package core

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type metadataFailureHostFileClient struct{ *moduleHostFileRPCClient }

func (metadataFailureHostFileClient) StatCallerHostPath(context.Context, string, bool) (*fstypes.Stat, error) {
	return nil, status.Error(codes.PermissionDenied, "fixture metadata failure")
}

func TestModuleHostFileReaderPreservesMetadataErrors(t *testing.T) {
	client := newModuleHostFileRPCClient(t)
	file := filepath.Join(t.TempDir(), "dagger.toml")
	require.NoError(t, os.WriteFile(file, []byte("readable contents"), 0o600))
	contents, err := client.ReadCallerHostFile(t.Context(), file)
	require.NoError(t, err)
	require.Equal(t, "readable contents", string(contents))

	data, found, err := readModuleHostFile(t.Context(), metadataFailureHostFileClient{client}, file)
	require.Equal(t, codes.PermissionDenied, status.Code(err))
	require.False(t, found)
	require.Empty(t, data)
}
