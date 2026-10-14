package core

import (
	"context"
	"os"
	"path/filepath"

	sdkcore "dagger.io/dagger/core"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

func (DirectorySuite) TestImportedUnchangedSubdirectoryDigestAfterFileEdit(ctx context.Context, t *testctx.T) {
	root := t.TempDir()
	for _, name := range []string{"base", "app"} {
		require.NoError(t, os.Mkdir(filepath.Join(root, name), 0755))
		require.NoError(t, os.WriteFile(filepath.Join(root, name, "lib.rs"), []byte("before"), 0644))
	}
	query := sdkcore.NewQuery(connect(ctx, t))
	source := query.Host().Directory(root)
	before, err := source.Directory("base").Digest(ctx)
	require.NoError(t, err)
	edited := source.WithNewFile("app/lib.rs", "after")
	contents, err := edited.File("app/lib.rs").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "after", contents)
	after, err := edited.Directory("base").Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, before, after, "editing another package must preserve unchanged imported hashes")
	contents, err = source.File("app/lib.rs").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "before", contents, "the imported snapshot must remain immutable")
}
