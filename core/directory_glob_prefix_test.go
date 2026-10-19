package core

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/containerd/containerd/v2/core/mount"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/util/patternmatcher"
	"github.com/stretchr/testify/require"
)

// Only the storage boundary is replaced: the test runs Directory.Glob's real
// walk on a local directory without requiring a privileged bind mount.
type globPrefixRef struct {
	bkcache.ImmutableRef
	root string
}

func (r globPrefixRef) ID() string                    { return "" }
func (r globPrefixRef) SnapshotID() string            { return "" }
func (r globPrefixRef) Release(context.Context) error { return nil }
func (r globPrefixRef) Mount(context.Context, bool) (bkcache.MountableRef, error) {
	return globPrefixMount{r.root}, nil
}

type globPrefixMount struct{ root string }

func (m globPrefixMount) Mount() ([]mount.Mount, func() error, error) {
	return []mount.Mount{{Type: "bind", Source: m.root}}, func() error { return nil }, nil
}

func globPrefixDirectory(t testing.TB, root string) (context.Context, *Directory, dagql.ObjectResult[*Directory]) {
	t.Helper()
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "glob", SessionID: "glob"})
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	ctx = dagql.ContextWithCache(ctx, cache)
	srv, err := dagql.NewServer(ctx, &Query{})
	require.NoError(t, err)
	dagql.Fields[*Directory]{}.Install(srv)
	dir := &Directory{Dir: new(LazyAccessor[string, *Directory]), Snapshot: new(LazyAccessor[bkcache.ImmutableRef, *Directory])}
	dir.SetPath("/")
	dir.SetSnapshot(globPrefixRef{root: root})
	dagql.Fields[*Query]{dagql.Func("fixture", func(context.Context, *Query, struct{}) (*Directory, error) {
		return dir, nil
	})}.Install(srv)
	var result dagql.ObjectResult[*Directory]
	require.NoError(t, srv.Select(ctx, srv.Root(), &result, dagql.Selector{Field: "fixture"}))
	ctx = dagql.ContextWithCall(ctx, &dagql.ResultCall{View: "v1.0.0-beta.15"})
	return ctx, dir, result
}

// The reference deliberately visits every entry. The optimized walk must return
// exactly the same paths in the same order, for both directory-slash views.
func globPrefixFullWalk(ctx context.Context, root, pattern string, slash bool) ([]string, error) {
	pat, err := patternmatcher.NewPattern(pattern)
	if err != nil {
		return nil, err
	}
	matches := []string{}
	err = filepath.WalkDir(root, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		name, err = filepath.Rel(root, name)
		if err != nil || name == "." {
			return err
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		match, err := pat.Match(name)
		if err != nil {
			return err
		}
		if match {
			if slash && entry.IsDir() {
				name += "/"
			}
			matches = append(matches, name)
		}
		return nil
	})
	return matches, err
}

func TestDirectoryGlobNativePrefix(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{
		"a.go", "a/a_test.go", "a/b/keep.go", "a/b/c/deep.go", "a/bb.go",
		"a/bb/sibling_test.go", "a/beta/pkg_test.go", "a/α/π_test.go",
		"a/[bracket]/literal.go", "a-extra/pkg_test.go", "z/deep/other_test.go",
	} {
		name = filepath.Join(root, filepath.FromSlash(name))
		require.NoError(t, os.MkdirAll(filepath.Dir(name), 0755))
		require.NoError(t, os.WriteFile(name, nil, 0600))
	}
	patterns := []string{
		"a/*_test.go", "a/**/*.go", "a/*/*.go", "a/b?/*.go", "a/[bc]/*.go",
		"*/b/*.go", "**/*.go", "a/*/**", "a/*/*", "missing/*.go", "a", "a/**",
		"a-extra/*.go", "!a/*.go", "[a]*/*.go", "a/α/*.go", "link/child/*.go",
		"/a/*.go", "../a/*.go", "a/./b/*.go", "a/b/../*.go",
	}
	if runtime.GOOS != "windows" {
		outside := t.TempDir()
		require.NoError(t, os.MkdirAll(filepath.Join(outside, "child"), 0755))
		require.NoError(t, os.WriteFile(filepath.Join(outside, "child", "outside.go"), nil, 0600))
		require.NoError(t, os.Symlink(outside, filepath.Join(root, "link")))
		patterns = append(patterns, `a/\[bracket\]/*.go`)
	}
	ctx, dir, result := globPrefixDirectory(t, root)
	for _, slash := range []bool{false, true} {
		view := "v0.16.0"
		if slash {
			view = "v1.0.0-beta.15"
		}
		ctx := dagql.ContextWithCall(ctx, &dagql.ResultCall{View: call.View(view)})
		for _, pattern := range patterns {
			t.Run(view+"/"+pattern, func(t *testing.T) {
				want, err := globPrefixFullWalk(ctx, root, pattern, slash)
				require.NoError(t, err)
				got, err := dir.Glob(ctx, result, pattern)
				require.NoError(t, err)
				require.Equal(t, want, got)
			})
		}
	}
	t.Run("canceled", func(t *testing.T) {
		ctx, cancel := context.WithCancel(ctx)
		cancel()
		_, err := dir.Glob(ctx, result, "missing/*.go")
		require.ErrorIs(t, err, context.Canceled)
	})
	t.Run("invalid pattern", func(t *testing.T) {
		_, err := dir.Glob(ctx, result, "a/[")
		require.Error(t, err)
	})
	t.Run("missing root", func(t *testing.T) {
		dir.SetPath("/missing")
		_, err := dir.Glob(ctx, result, "**/*.go")
		require.ErrorIs(t, err, os.ErrNotExist)
	})
}

func BenchmarkDirectoryGlobNativePrefix(b *testing.B) {
	root := b.TempDir()
	for branch := range 24 {
		for pkg := range 24 {
			dir := filepath.Join(root, fmt.Sprintf("module%02d", branch), fmt.Sprintf("pkg%02d", pkg))
			require.NoError(b, os.MkdirAll(dir, 0755))
			for file := range 8 {
				require.NoError(b, os.WriteFile(filepath.Join(dir, fmt.Sprintf("file%02d_test.go", file)), nil, 0600))
			}
		}
	}
	ctx, dir, result := globPrefixDirectory(b, root)
	for _, pattern := range []string{"module00/pkg00/*_test.go", "module00/**/*.go", "**/*.go"} {
		b.Run(pattern, func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				got, err := dir.Glob(ctx, result, pattern)
				if err != nil {
					b.Fatal(err)
				}
				if len(got) == 0 {
					b.Fatal("missing glob results")
				}
			}
		})
	}
}
