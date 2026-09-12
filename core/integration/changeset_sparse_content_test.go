package core

import (
	"context"
	"os"
	"path/filepath"

	"dagger.io/dagger"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

// A stat-sensitive snapshot diff is not the changeset's semantic write set.
// Applying an unrelated change must neither add nor overwrite unchanged files.
func (ChangesetSuite) TestWithChangesIgnoresStatOnlySiblings(ctx context.Context, t *testctx.T) {
	c := connect(ctx, t)
	before := c.Directory().
		WithNewFile("debug/app", "old app", dagger.DirectoryWithNewFileOpts{Permissions: 0o751}).
		WithNewFile("debug/lib.a", "unchanged library").
		WithNewFile("debug/literal*.txt", "old literal").
		WithNewFile("debug/literal-other.txt", "unchanged other")
	after := before.WithTimestamps(1700000000).
		WithNewFile("debug/app", "new app", dagger.DirectoryWithNewFileOpts{Permissions: 0o751}).
		WithNewFile("debug/literal*.txt", "new literal")
	// withNewFile retains an existing file's mode. Establish the desired
	// source mode on creation, and verify it before testing changeset copying.
	sourceInfo, err := after.Stat(ctx, "debug/app")
	require.NoError(t, err)
	sourceMode, err := sourceInfo.Permissions(ctx)
	require.NoError(t, err)
	require.Equal(t, 0o751, sourceMode)
	changes := after.Changes(before)
	modified, err := changes.ModifiedPaths(ctx)
	require.NoError(t, err)
	require.ElementsMatch(t, []string{"debug/app", "debug/literal*.txt"}, modified)
	// Pin the motivating precondition rather than accidentally testing a
	// materialization whose unchanged siblings were content-coalesced away.
	phantoms, err := before.Diff(after).Directory("debug").Entries(ctx)
	require.NoError(t, err)
	require.Contains(t, phantoms, "lib.a")

	for _, existingLibrary := range []bool{false, true} {
		base := c.Directory().WithNewFile("debug/app", "host app")
		if existingLibrary {
			base = base.WithNewFile("debug/lib.a", "independent host edit")
		}
		result := base.WithChanges(changes)
		entries, err := result.Directory("debug").Entries(ctx)
		require.NoError(t, err)
		want := []string{"app", "literal*.txt"}
		if existingLibrary {
			want = append(want, "lib.a")
			got, err := result.File("debug/lib.a").Contents(ctx)
			require.NoError(t, err)
			require.Equal(t, "independent host edit", got)
		}
		require.ElementsMatch(t, want, entries)
		dest := t.TempDir()
		_, err = result.Export(ctx, dest)
		require.NoError(t, err)
		info, err := os.Stat(filepath.Join(dest, "debug/app"))
		require.NoError(t, err)
		require.Equal(t, os.FileMode(0o751), info.Mode().Perm())
		got, err := os.ReadFile(filepath.Join(dest, "debug/literal*.txt"))
		require.NoError(t, err)
		require.Equal(t, "new literal", string(got))
	}
}

// Only's empty set must not mean an unfiltered copy. A removal-only changeset
// with stat-only siblings cannot add or overwrite those siblings either.
func (ChangesetSuite) TestWithChangesRemovalIgnoresStatOnlySiblings(ctx context.Context, t *testctx.T) {
	c := connect(ctx, t)
	before := c.Directory().WithNewFile("remove", "old").WithNewFile("keep", "same")
	after := before.WithTimestamps(1700000000).WithoutFile("remove")
	changes := after.Changes(before)
	base := c.Directory().WithNewFile("remove", "host old").WithNewFile("keep", "host edit")
	result := base.WithChanges(changes)
	entries, err := result.Entries(ctx)
	require.NoError(t, err)
	require.Equal(t, []string{"keep"}, entries)
	got, err := result.File("keep").Contents(ctx)
	require.NoError(t, err)
	require.Equal(t, "host edit", got)
}
