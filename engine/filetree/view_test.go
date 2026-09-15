package filetree

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"strings"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/opencontainers/go-digest"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
	"github.com/stretchr/testify/require"
)

type viewReadCounter struct {
	content.Store
	reads map[digest.Digest]int
}

func (s *viewReadCounter) ReaderAt(ctx context.Context, desc ocispec.Descriptor) (content.ReaderAt, error) {
	s.reads[desc.Digest]++
	return s.Store.ReaderAt(ctx, desc)
}

func putViewTree(t *testing.T, in *Ingest, metadata Metadata, entries ...Entry) Object {
	t.Helper()
	obj, err := in.PutTree(Tree{Version: TreeVersion, Metadata: metadata, Entries: entries})
	require.NoError(t, err)
	return obj
}

func readViewFile(t *testing.T, view *View, name string) string {
	t.Helper()
	r, err := view.Open(name)
	require.NoError(t, err)
	data, err := io.ReadAll(r)
	require.NoError(t, errors.Join(err, r.Close()))
	return string(data)
}

func nestedTestView(t *testing.T) (*View, context.Context) {
	t.Helper()
	f := newTestStore(t)
	in := f.ingest(t, "view")
	file, err := in.PutFile(strings.NewReader("source"), 6)
	require.NoError(t, err)
	metadata := Metadata{Mode: 0o644}
	child := putViewTree(t, in, Metadata{Mode: 0o755},
		Entry{Name: []byte("a"), Kind: File, Metadata: &metadata, Object: &file},
		Entry{Name: []byte("z"), Kind: File, Metadata: &metadata, Object: &file})
	root := putViewTree(t, in, Metadata{Mode: 0o755},
		Entry{Name: []byte("dir"), Kind: Directory, Object: &child},
		Entry{Name: []byte("dir-plain"), Kind: File, Metadata: &metadata, Object: &file},
		Entry{Name: []byte("other"), Kind: Directory, Object: &child})
	counter := &viewReadCounter{Store: f.store.blobs, reads: make(map[digest.Digest]int)}
	v, err := NewView(f.ctx, NewStore(counter), root)
	require.NoError(t, err)
	require.Equal(t, map[digest.Digest]int{root.Digest: 1, child.Digest: 1}, counter.reads,
		"reused nodes are read once; constructing a view does not read file payloads")
	require.Equal(t, root, v.Root())
	return v, f.ctx
}

func TestViewNestedReusedTrees(t *testing.T) {
	v, ctx := nestedTestView(t)
	expectedEntries := []string{"dir", "dir-plain", "dir/a", "dir/z", "other", "other/a", "other/z"}
	require.Equal(t, expectedEntries, v.Entries())
	entries := v.Entries()
	entries[0] = "mutated"
	require.Equal(t, expectedEntries, v.Entries())
	for _, root := range []string{"", ".", "/"} {
		var paths []string
		require.NoError(t, v.Walk(ctx, root, func(name string, entry fs.DirEntry, err error) error {
			require.NoError(t, err)
			info, err := entry.Info()
			require.NoError(t, err)
			require.Equal(t, name, info.Sys().(*types.Stat).Path)
			paths = append(paths, name)
			return nil
		}))
		require.Equal(t, []string{"dir", "dir/a", "dir/z", "dir-plain", "other", "other/a", "other/z"}, paths)
		info, err := v.Stat(root)
		require.NoError(t, err)
		require.True(t, info.IsDir())
	}
	require.Equal(t, "source", readViewFile(t, v, "other/z"))
}

func TestViewWalkSkipSemantics(t *testing.T) {
	v, ctx := nestedTestView(t)
	for _, tc := range []struct {
		name, target, skip string
		signal             error
		want               []string
	}{
		{"directory", "", "dir", fs.SkipDir, []string{"dir", "dir-plain", "other", "other/a", "other/z"}},
		{"file", "", "dir/a", fs.SkipDir, []string{"dir", "dir/a", "dir-plain", "other", "other/a", "other/z"}},
		{"all", "", "dir/a", fs.SkipAll, []string{"dir", "dir/a"}},
		{"subtree", "dir", "", nil, []string{"dir", "dir/a", "dir/z"}},
		{"single-file", "dir/a", "dir/a", fs.SkipDir, []string{"dir/a"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var paths []string
			err := v.Walk(ctx, tc.target, func(name string, _ fs.DirEntry, err error) error {
				require.NoError(t, err)
				paths = append(paths, name)
				if name == tc.skip {
					return tc.signal
				}
				return nil
			})
			require.NoError(t, err)
			require.Equal(t, tc.want, paths)
		})
	}
	stop := errors.New("callback failure")
	require.ErrorIs(t, v.Walk(ctx, "", func(string, fs.DirEntry, error) error { return stop }), stop)
}

func TestViewMetadataBytesAndHardlinks(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "bytes")
	file, err := in.PutFile(strings.NewReader("payload"), 7)
	require.NoError(t, err)
	name := string([]byte{'f', 0xff})
	xattr := string([]byte{'u', '=', 0xfe})
	metadata := Metadata{Mode: 0o7751, UID: 123, GID: 456, ModTime: -123456789,
		Xattrs: []Xattr{{Name: []byte(xattr), Value: []byte{0, 0xff, 1}}}}
	child := putViewTree(t, in, metadata, Entry{Name: []byte(name), Kind: File, Metadata: &metadata, Object: &file})
	target := "nested/" + name
	link := []byte{'/', 'o', 'u', 't', '/', 0xfd}
	root := putViewTree(t, in, metadata,
		Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte(target)},
		Entry{Name: []byte("nested"), Kind: Directory, Object: &child},
		Entry{Name: []byte("symlink"), Kind: Symlink, Metadata: &metadata, Linkname: link})
	v, err := NewView(f.ctx, f.store, root)
	require.NoError(t, err)
	for _, name := range []string{target, "alias", "nested", "."} {
		info, err := v.Stat(name)
		require.NoError(t, err)
		require.Equal(t, os.FileMode(0o751), info.Mode().Perm())
		require.Equal(t, os.ModeSetuid|os.ModeSetgid|os.ModeSticky, info.Mode()&(os.ModeSetuid|os.ModeSetgid|os.ModeSticky))
		require.EqualValues(t, 123, info.Uid)
		require.EqualValues(t, 456, info.Gid)
		require.Equal(t, metadata.ModTime, info.ModTime().UnixNano())
		require.Equal(t, []byte{0, 0xff, 1}, info.Xattrs[xattr])
		info.Xattrs[xattr][0] = 99
		info.Stat.Path = "changed"
	}
	alias, err := v.Stat("alias")
	require.NoError(t, err)
	require.Equal(t, target, alias.Linkname)
	require.EqualValues(t, 7, alias.Size())
	require.Equal(t, "payload", readViewFile(t, v, "alias"))
	require.Equal(t, "payload", readViewFile(t, v, target))
	symlink, err := v.Stat("symlink")
	require.NoError(t, err)
	require.Equal(t, string(link), symlink.Linkname)
	require.NotZero(t, symlink.Mode()&os.ModeSymlink)
	_, err = v.Open("symlink")
	require.ErrorIs(t, err, fs.ErrInvalid, "never follow symlink targets")
	_, err = v.Open("nested")
	require.ErrorIs(t, err, fs.ErrInvalid)
}

func TestViewRejectsIndirectOrMissingHardlinks(t *testing.T) {
	for _, target := range []string{"missing", "directory", "symlink", "other-link", "alias", "symlink/child"} {
		t.Run(target, func(t *testing.T) {
			f := newTestStore(t)
			in := f.ingest(t, "invalid-link")
			file, err := in.PutFile(strings.NewReader("file"), 4)
			require.NoError(t, err)
			metadata := Metadata{Mode: 0o755}
			child := putViewTree(t, in, metadata)
			root := putViewTree(t, in, metadata,
				Entry{Name: []byte("file"), Kind: File, Metadata: &metadata, Object: &file},
				Entry{Name: []byte("directory"), Kind: Directory, Object: &child},
				Entry{Name: []byte("symlink"), Kind: Symlink, Metadata: &metadata, Linkname: []byte("directory")},
				Entry{Name: []byte("other-link"), Kind: Hardlink, Linkname: []byte("file")},
				Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte(target)})
			_, err = NewView(f.ctx, f.store, root)
			require.ErrorContains(t, err, "must target a regular file directly")
		})
	}
}

func TestViewPathsAndCancellation(t *testing.T) {
	v, ctx := nestedTestView(t)
	for _, invalid := range []string{"../dir", "dir/../other", "./dir", "dir//a", "dir/", "/dir", "dir\x00a"} {
		_, err := v.Stat(invalid)
		require.ErrorIs(t, err, fs.ErrInvalid)
		_, err = v.Open(invalid)
		require.ErrorIs(t, err, fs.ErrInvalid)
		require.ErrorIs(t, v.Walk(ctx, invalid, func(string, fs.DirEntry, error) error {
			t.Fatal("invalid path reached callback")
			return nil
		}), fs.ErrInvalid)
	}
	_, err := v.Stat("missing")
	require.ErrorIs(t, err, fs.ErrNotExist)
	called := false
	require.NoError(t, v.Walk(ctx, "missing", func(name string, entry fs.DirEntry, err error) error {
		called = true
		require.Equal(t, "missing", name)
		require.Nil(t, entry)
		require.ErrorIs(t, err, fs.ErrNotExist)
		return nil
	}))
	require.True(t, called)
	canceled, cancel := context.WithCancel(ctx)
	cancel()
	_, err = NewView(canceled, v.store, v.Root())
	require.ErrorIs(t, err, context.Canceled)
	require.ErrorIs(t, v.Walk(canceled, "", func(string, fs.DirEntry, error) error { return nil }), context.Canceled)
	readCtx, cancelRead := context.WithCancel(ctx)
	defer cancelRead()
	readView, err := NewView(readCtx, v.store, v.Root())
	require.NoError(t, err)
	r, err := readView.Open("dir/a")
	require.NoError(t, err)
	cancelRead()
	_, err = io.ReadAll(r)
	require.ErrorIs(t, err, context.Canceled)
	require.NoError(t, r.Close())
	_, err = readView.Open("dir/a")
	require.ErrorIs(t, err, context.Canceled)
}
