package filesync

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	contenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
)

func TestSyncScopedHardlinkDigests(t *testing.T) {
	for _, copyPath := range []string{"", "project"} {
		t.Run("copyPath="+copyPath, func(t *testing.T) {
			store := testutil.NewStore(t)
			root := writeTree(t, map[string]string{"project/a-file": "first contents"})
			assert.NilError(t, os.Link(filepath.Join(root, "project/a-file"), filepath.Join(root, "project/z-link")))
			assert.NilError(t, os.Symlink("project/a-file", filepath.Join(root, "project/symlink")))
			base, err := fsutil.NewFS(root)
			assert.NilError(t, err)
			includes := []string{"!*", "project"}
			filtered, err := fsutil.NewFilterFS(base, &fsutil.FilterOpt{IncludePatterns: includes})
			assert.NilError(t, err)
			// The sender resets hardlink targets after filtering too.
			client := fsutil.WithHardlinkReset(filtered)
			local, err := newLocalFS(NewMirrorSharedState(t.TempDir()), "", includes, nil, nil, copyPath)
			assert.NilError(t, err)
			prefix := "project/"
			if copyPath != "" {
				prefix = ""
			}
			var previous digest.Digest
			for _, contents := range []string{"first contents", "changed and longer contents"} {
				assert.NilError(t, os.WriteFile(filepath.Join(root, "project/a-file"), []byte(contents), 0o644))
				ref, owner := syncPublished(t, store, local, client)
				t.Cleanup(func() {
					assert.NilError(t, ref.Release(context.Background()))
					assert.NilError(t, store.Manager.RemoveLease(context.Background(), owner))
				})
				// Check physical data before consulting imported hash records.
				assertSyncedFile(t, ref, prefix+"a-file", contents)
				assertSyncedFile(t, ref, prefix+"z-link", contents)
				link, err := os.Readlink(filepath.Join(testutil.Root(t, ref), prefix+"symlink"))
				assert.NilError(t, err)
				assert.Equal(t, link, "project/a-file")
				source, err := contenthash.Checksum(context.Background(), ref, "/"+prefix+"a-file", contenthash.ChecksumOpts{})
				assert.NilError(t, err)
				alias, err := contenthash.Checksum(context.Background(), ref, "/"+prefix+"z-link", contenthash.ChecksumOpts{})
				assert.NilError(t, err)
				assert.Equal(t, alias, source, "a hardlink must use its target's content digest")
				if previous != "" {
					assert.Assert(t, alias != previous, "editing the inode must change the hardlink's digest")
				}
				previous = alias
			}
		})
	}
}
