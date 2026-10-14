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
	require.NoError(t, os.Symlink("lib.rs", filepath.Join(root, "app", "link.rs")))
	query := sdkcore.NewQuery(connect(ctx, t))
	source := query.Host().Directory(root)
	before, err := source.Directory("base").Digest(ctx)
	require.NoError(t, err)
	for _, filename := range []string{"app/lib.rs", "app/new.rs", "new/deep/file.rs", "app/link.rs"} {
		edited := source.WithNewFile(filename, "after")
		contents, err := edited.File(filename).Contents(ctx)
		require.NoError(t, err)
		require.Equal(t, "after", contents)
		after, err := edited.Directory("base").Digest(ctx)
		require.NoError(t, err)
		require.Equal(t, before, after, "writing %s must preserve unchanged imported hashes", filename)
		parentDigest, err := source.Digest(ctx)
		require.NoError(t, err)
		childDigest, err := edited.Digest(ctx)
		require.NoError(t, err)
		require.NotEqual(t, parentDigest, childDigest, "writing %s must update the complete digest", filename)
	}
	projected := source.Directory("app").WithNewFile("lib.rs", "after")
	projectedDigest, err := projected.Digest(ctx)
	require.NoError(t, err)
	rootEditDigest, err := source.WithNewFile("app/lib.rs", "after").Directory("app").Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, rootEditDigest, projectedDigest, "a projected directory must invalidate the resolved file path")
	contents, err := source.File("app/lib.rs").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "before", contents, "the imported snapshot must remain immutable")
}

func (DirectorySuite) TestFileWriteWithHardLinks(ctx context.Context, t *testctx.T) {
	query := sdkcore.NewQuery(connect(ctx, t))
	source := query.Container().From(alpineImage).
		WithExec([]string{"sh", "-c", "mkdir /data; printf before > /data/file; ln /data/file /data/alias"}).
		Directory("/data")
	before, err := source.File("alias").Digest(ctx)
	require.NoError(t, err)
	edited := source.WithNewFile("file", "after")
	contents, err := edited.File("alias").Contents(ctx)
	require.NoError(t, err)
	after, err := edited.File("alias").Digest(ctx)
	require.NoError(t, err)
	// Copy-up can split the links. The hash must reflect whether this
	// snapshotter also changed the alias's contents.
	if contents == "before" {
		require.Equal(t, before, after)
	} else {
		require.Equal(t, "after", contents)
		require.NotEqual(t, before, after)
	}
	contents, err = edited.File("file").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "after", contents)
	contents, err = source.File("alias").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "before", contents)
}
