package contenthash

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/dagger/dagger/util/layercopy"
	"gotest.tools/v3/assert"
)

var configIncludes = []string{"**/Cargo.toml", "**/Cargo.lock", "**/rust-toolchain", "**/rust-toolchain.toml", "**/.cargo/**"}

func TestChecksumEntriesMatchesFilteredCopy(t *testing.T) {
	root := t.TempDir()
	for p, contents := range map[string]string{
		"workspace/Cargo.toml":              "workspace",
		"workspace/member/Cargo.toml":       "member",
		"workspace/member/src/lib.rs":       "unselected",
		"workspace/.cargo/config.toml":      "configuration",
		"workspace/.cargo/ignored.toml":     "excluded",
		"workspace/deep/.cargo/nested/data": "resource",
		"workspace/rust-toolchain.toml":     "toolchain",
		"other/Cargo.toml":                  "outside scope",
	} {
		writeFile(t, root, p, contents)
	}
	assert.NilError(t, os.MkdirAll(filepath.Join(root, "workspace/.cargo/empty"), 0o751))
	assert.NilError(t, os.Chmod(filepath.Join(root, "workspace/member"), 0o750))
	assert.NilError(t, os.Symlink("missing", filepath.Join(root, "workspace/Cargo.lock")))
	assert.NilError(t, os.Symlink("workspace", filepath.Join(root, "alias")))
	opts := ChecksumOpts{EntryPaths: true, IncludePatterns: configIncludes, ExcludePatterns: []string{"**/ignored.toml"}}
	for _, scope := range []string{"/", "/workspace", "/alias"} {
		t.Run(scope, func(t *testing.T) {
			dest := t.TempDir()
			copier, err := layercopy.NewCopier(layercopy.Mount{Root: dest})
			assert.NilError(t, err)
			assert.NilError(t, copier.Copy(t.Context(), layercopy.Mount{Root: root}, scope, "/", layercopy.CopyOptions{
				Filter:          layercopy.Filter{Include: opts.IncludePatterns, Exclude: opts.ExcludePatterns},
				CopyDirContents: true, ReplaceExisting: true,
			}))
			assert.NilError(t, copier.Close())
			want, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{dest}, "/", ChecksumOpts{EntryPaths: true})
			assert.NilError(t, err)
			got, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{root}, scope, opts)
			assert.NilError(t, err)
			assert.Equal(t, got, want)
		})
	}
}

func TestChecksumEntriesTracksConfiguration(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Cargo.toml", "manifest")
	writeFile(t, root, "member/Cargo.toml", "member")
	writeFile(t, root, "member/src/lib.rs", "before")
	opts := ChecksumOpts{EntryPaths: true, IncludePatterns: configIncludes}
	checksum := func() string {
		t.Helper()
		sum, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{root}, "/", opts)
		assert.NilError(t, err)
		return sum.String()
	}
	before := checksum()
	writeFile(t, root, "member/src/lib.rs", "after")
	assert.Equal(t, checksum(), before, "ordinary source contents are excluded")
	writeFile(t, root, "Cargo.toml", "changed")
	assert.Assert(t, checksum() != before, "manifest contents matter")
	before = checksum()
	assert.NilError(t, os.Chmod(filepath.Join(root, "member/Cargo.toml"), 0o640))
	assert.Assert(t, checksum() != before, "file metadata matters")
	before = checksum()
	assert.NilError(t, os.Chmod(filepath.Join(root, "member"), 0o750))
	assert.Assert(t, checksum() != before, "containing-directory metadata matters")
	before = checksum()
	writeFile(t, root, ".cargo/config.toml", "new configuration")
	assert.Assert(t, checksum() != before, "added configuration matters")
	before = checksum()
	assert.NilError(t, os.Remove(filepath.Join(root, ".cargo/config.toml")))
	assert.Assert(t, checksum() != before, "removed configuration matters")
}

func TestChecksumEntriesIncludesTreeStructure(t *testing.T) {
	a, b := t.TempDir(), t.TempDir()
	for _, root := range []string{a, b} {
		writeFile(t, root, "a/b/Cargo.toml", "first")
	}
	writeFile(t, a, "a/c/Cargo.toml", "second")
	writeFile(t, b, "a/b/c/Cargo.toml", "second")
	opts := ChecksumOpts{EntryPaths: true, IncludePatterns: configIncludes}
	x, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{a}, "/", opts)
	assert.NilError(t, err)
	y, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{b}, "/", opts)
	assert.NilError(t, err)
	assert.Assert(t, x != y, "equal basenames in different tree structures must remain distinct")
}

func TestChecksumEntriesEmptyAndInvalid(t *testing.T) {
	root := t.TempDir()
	cc := newTestCacheContext(t)
	empty, err := cc.Checksum(t.Context(), bindMountable{root}, "/", ChecksumOpts{EntryPaths: true})
	assert.NilError(t, err)
	assert.Equal(t, empty, checksumEntries("/", nil))
	writeFile(t, root, "file", "data")
	for _, opts := range []ChecksumOpts{
		{EntryPaths: true, IncludePatterns: []string{"["}},
		{EntryPaths: true, ExcludePatterns: []string{"["}},
		{EntryPaths: true, Wildcard: true},
	} {
		_, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{root}, "/", opts)
		assert.Assert(t, err != nil)
	}
	for _, scope := range []string{"/file", "/missing"} {
		_, err := newTestCacheContext(t).Checksum(t.Context(), bindMountable{root}, scope, ChecksumOpts{EntryPaths: true})
		assert.Assert(t, err != nil)
	}
}

func BenchmarkConfigurationChecksum(b *testing.B) {
	root := b.TempDir()
	for i := range 1024 {
		dir := filepath.Join(root, fmt.Sprintf("crate_%04d", i))
		assert.NilError(b, os.MkdirAll(filepath.Join(dir, "src"), 0o755))
		assert.NilError(b, os.WriteFile(filepath.Join(dir, "Cargo.toml"), []byte("manifest"), 0o644))
		assert.NilError(b, os.WriteFile(filepath.Join(dir, "src/lib.rs"), []byte("source"), 0o644))
	}
	ctx := context.Background()
	cc, err := newCacheContext(testRefMetadata{})
	assert.NilError(b, err)
	_, err = cc.Checksum(ctx, bindMountable{root}, "/", ChecksumOpts{})
	assert.NilError(b, err)
	b.Run("native_records", func(b *testing.B) {
		b.ReportAllocs()
		for b.Loop() {
			_, err := cc.Checksum(ctx, bindMountable{root}, "/", ChecksumOpts{EntryPaths: true, IncludePatterns: configIncludes})
			assert.NilError(b, err)
		}
	})
	b.Run("filtered_copy", func(b *testing.B) {
		dest := filepath.Join(b.TempDir(), "filtered")
		b.ReportAllocs()
		for b.Loop() {
			b.StopTimer()
			assert.NilError(b, os.RemoveAll(dest))
			assert.NilError(b, os.Mkdir(dest, 0o755))
			b.StartTimer()
			copier, err := layercopy.NewCopier(layercopy.Mount{Root: dest})
			assert.NilError(b, err)
			assert.NilError(b, copier.Copy(ctx, layercopy.Mount{Root: root}, "/", "/", layercopy.CopyOptions{Filter: layercopy.Filter{Include: configIncludes}, CopyDirContents: true, ReplaceExisting: true}))
			assert.NilError(b, copier.Close())
			copied, err := newCacheContext(testRefMetadata{})
			assert.NilError(b, err)
			_, err = copied.Checksum(ctx, bindMountable{dest}, "/", ChecksumOpts{})
			assert.NilError(b, err)
		}
	})
}
