//go:build linux

package filetree

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/continuity/sysx"
	"github.com/opencontainers/go-digest"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
	"github.com/stretchr/testify/require"
)

func materializeTestMetadata() Metadata {
	return Metadata{Mode: 0o755, UID: uint32(os.Getuid()), GID: uint32(os.Getgid()), ModTime: -123456789}
}

func materializeTestFile(t *testing.T, in *Ingest, name, value string) Entry {
	t.Helper()
	obj, err := in.PutFile(strings.NewReader(value), int64(len(value)))
	require.NoError(t, err)
	md := materializeTestMetadata()
	md.Mode = 0o644
	return Entry{Name: []byte(name), Kind: File, Metadata: &md, Object: &obj}
}

func materializeTestView(t *testing.T, f *testStore, in *Ingest, metadata Metadata, entries ...Entry) *View {
	t.Helper()
	obj, err := in.PutTree(Tree{Version: TreeVersion, Metadata: metadata, Entries: entries})
	require.NoError(t, err)
	view, err := NewView(f.ctx, f.store, obj)
	require.NoError(t, err)
	return view
}

func assertMaterialized(t *testing.T, destination string, view *View) {
	t.Helper()
	var actual []string
	require.NoError(t, filepath.WalkDir(destination, func(name string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(destination, name)
		if err != nil {
			return err
		}
		actual = append(actual, rel)
		return nil
	}))
	require.ElementsMatch(t, append(view.Entries(), "."), actual)
	for _, name := range actual {
		p := filepath.Join(destination, name)
		info, err := os.Lstat(p)
		require.NoError(t, err)
		want, err := view.Stat(name)
		require.NoError(t, err)
		require.Equal(t, want.Mode(), info.Mode(), name)
		require.Equal(t, want.ModTime().UnixNano(), info.ModTime().UnixNano(), name)
		system := info.Sys().(*syscall.Stat_t)
		require.Equal(t, want.Uid, system.Uid, name)
		require.Equal(t, want.Gid, system.Gid, name)
		attrs, err := sysx.LListxattr(p)
		require.NoError(t, err)
		require.Len(t, attrs, len(want.Xattrs), name)
		for key, expected := range want.Xattrs {
			got, err := sysx.LGetxattr(p, key)
			require.NoError(t, err)
			require.Equal(t, expected, got, name+":"+key)
		}
		switch {
		case info.Mode().IsRegular():
			reader, err := view.Open(name)
			require.NoError(t, err)
			expected, err := io.ReadAll(reader)
			require.NoError(t, errors.Join(err, reader.Close()))
			got, err := os.ReadFile(p)
			require.NoError(t, err)
			require.Equal(t, expected, got, name)
			if want.Linkname != "" {
				target, err := os.Stat(filepath.Join(destination, want.Linkname))
				require.NoError(t, err)
				require.True(t, os.SameFile(info, target), name)
			}
		case info.Mode()&os.ModeSymlink != 0:
			target, err := os.Readlink(p)
			require.NoError(t, err)
			require.Equal(t, want.Linkname, target)
		}
	}
}

func TestMaterializeReconstructAndDelta(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "materialize")
	md := materializeTestMetadata()
	md.Xattrs = []Xattr{{Name: []byte("user.example=raw"), Value: []byte{0, 255, 42}}}
	file := materializeTestFile(t, in, "file", "old payload")
	file.Metadata.Mode = 0o6751
	file.Metadata.Xattrs = md.Xattrs
	sub := materializeTestView(t, f, in, md, file)
	linkMD := materializeTestMetadata()
	linkMD.Mode = 0o777
	before := materializeTestView(t, f, in, md,
		Entry{Name: []byte("dir"), Kind: Directory, Object: &sub.root},
		Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte("dir/file")},
		Entry{Name: []byte("link"), Kind: Symlink, Metadata: &linkMD, Linkname: []byte("/not/a/target")},
		materializeTestFile(t, in, ".wh.", "literal, not a whiteout"),
		materializeTestFile(t, in, ".wh..wh..opq", "literal, not opacity"),
		materializeTestFile(t, in, "\x01\xffraw", "raw name"),
		materializeTestFile(t, in, "unchanged", "retained bytes"),
	)
	destination := t.TempDir()
	require.NoError(t, Materialize(f.ctx, destination, nil, before))
	assertMaterialized(t, destination, before)
	unchangedInfo, err := os.Stat(filepath.Join(destination, "unchanged"))
	require.NoError(t, err)

	md.Xattrs = nil // absent old root/directory xattrs must be removed
	file = materializeTestFile(t, in, "file", "new payload")
	sub = materializeTestView(t, f, in, md, file)
	after := materializeTestView(t, f, in, md,
		Entry{Name: []byte("dir"), Kind: Directory, Object: &sub.root},
		Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte("dir/file")},
		materializeTestFile(t, in, "link", "replaced symlink"),
		materializeTestFile(t, in, "unchanged", "retained bytes"),
	)
	guard := &guardContentStore{Store: f.store.blobs, forbidden: before.entries["unchanged"].object.Digest}
	after.store = NewStore(guard)
	require.NoError(t, Materialize(f.ctx, destination, before, after))
	require.Zero(t, guard.reads, "delta must not open unchanged payloads")
	after.store = f.store
	assertMaterialized(t, destination, after)
	current, err := os.Stat(filepath.Join(destination, "unchanged"))
	require.NoError(t, err)
	require.True(t, os.SameFile(unchangedInfo, current), "unchanged inode must not be recreated")

	// Reconstruction has no dependency on the original source or old snapshot.
	reconstructed := t.TempDir()
	require.NoError(t, Materialize(f.ctx, reconstructed, nil, after))
	assertMaterialized(t, reconstructed, after)
}

func TestMaterializeDirectoryReplacementAndAlias(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "replacement")
	md := materializeTestMetadata()
	sub := materializeTestView(t, f, in, md, materializeTestFile(t, in, "child", "old"))
	before := materializeTestView(t, f, in, md,
		Entry{Name: []byte("a"), Kind: Directory, Object: &sub.root},
		Entry{Name: []byte("a-removed"), Kind: Directory, Object: &sub.root},
		materializeTestFile(t, in, "target", "same bytes"),
		Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte("target")},
	)
	destination := t.TempDir()
	require.NoError(t, Materialize(f.ctx, destination, nil, before))
	linkMD := md
	linkMD.Mode = 0o777
	target := materializeTestFile(t, in, "target", "same bytes")
	target.Metadata.Mode = 0o600 // replaced inode even with identical content
	after := materializeTestView(t, f, in, md,
		Entry{Name: []byte("a"), Kind: Symlink, Metadata: &linkMD, Linkname: []byte("../outside")},
		target,
		Entry{Name: []byte("alias"), Kind: Hardlink, Linkname: []byte("target")},
		Entry{Name: []byte("newdir"), Kind: Directory, Object: &sub.root},
	)
	require.NoError(t, Materialize(f.ctx, destination, before, after))
	assertMaterialized(t, destination, after)
	require.NoError(t, Materialize(f.ctx, destination, after, before))
	assertMaterialized(t, destination, before)
}

func TestMaterializeCancellationAndMissingPayload(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "missing")
	view := materializeTestView(t, f, in, materializeTestMetadata(), materializeTestFile(t, in, "file", "payload"))
	ctx, cancel := context.WithCancel(f.ctx)
	cancel()
	require.ErrorIs(t, Materialize(ctx, t.TempDir(), nil, view), context.Canceled)
	require.NoError(t, f.store.blobs.Delete(f.ctx, view.entries["file"].object.Digest))
	require.Error(t, Materialize(f.ctx, t.TempDir(), nil, view))
}

type guardContentStore struct {
	content.Store
	forbidden digest.Digest
	reads     int
}

func (s *guardContentStore) ReaderAt(ctx context.Context, desc ocispec.Descriptor) (content.ReaderAt, error) {
	if desc.Digest == s.forbidden {
		s.reads++
		return nil, errors.New("unchanged file opened")
	}
	return s.Store.ReaderAt(ctx, desc)
}
