package contenthash

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/dagger/dagger/engine/filetree"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/hashutil"
	iradix "github.com/hashicorp/go-immutable-radix/v2"
	"github.com/opencontainers/go-digest"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
	"github.com/stretchr/testify/require"
)

type fileTreeTestInfo struct {
	*fsutil.StatInfo
	hash digest.Digest
}

type fileTreeChecksumStore struct {
	content.Store
	root          filetree.Object
	tree          []byte
	checksums     filetree.Object
	payload       []byte
	checksumReads int
}

func (s *fileTreeChecksumStore) Info(_ context.Context, dgst digest.Digest) (content.Info, error) {
	if dgst != s.root.Digest {
		return content.Info{}, fmt.Errorf("unexpected Info %s", dgst)
	}
	return content.Info{Digest: dgst, Size: s.root.Size, Labels: map[string]string{
		"dagger.io/filetree.version":                     "1",
		"containerd.io/gc.ref.content.dagger.filetree.0": s.checksums.Digest.String(),
	}}, nil
}

type fileTreeChecksumReader struct{ *bytes.Reader }

func (*fileTreeChecksumReader) Close() error { return nil }

func (s *fileTreeChecksumStore) ReaderAt(_ context.Context, desc ocispec.Descriptor) (content.ReaderAt, error) {
	if desc.Digest == s.root.Digest {
		return &fileTreeChecksumReader{bytes.NewReader(s.tree)}, nil
	}
	if desc.Digest != s.checksums.Digest {
		return nil, fmt.Errorf("unexpected ReaderAt %s", desc.Digest)
	}
	s.checksumReads++
	return &fileTreeChecksumReader{bytes.NewReader(s.payload)}, nil
}

func TestFileTreeChecksumSidecarReadValidation(t *testing.T) {
	for _, test := range []struct {
		name    string
		size    int64
		payload []byte
		reads   int
	}{
		{name: "oversized", size: maxFileTreeChecksumsSize + 1},
		{name: "wrong size", size: 8, payload: []byte("short"), reads: 1},
		{name: "wrong digest", size: 5, payload: []byte("wrong"), reads: 1},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := &fileTreeChecksumStore{checksums: filetree.Object{Digest: digest.FromString("valid"), Size: test.size}, payload: test.payload}
			var err error
			store.tree, err = filetree.Encode(filetree.Tree{Version: filetree.TreeVersion, Checksums: &store.checksums})
			require.NoError(t, err)
			store.root = filetree.Object{Digest: digest.FromBytes(store.tree), Size: int64(len(store.tree))}
			require.Error(t, RestoreFileTreeCacheContext(t.Context(), store, store.root, nil, ""))
			require.Equal(t, test.reads, store.checksumReads)
		})
	}
}

func (info fileTreeTestInfo) Digest() digest.Digest { return info.hash }

func testFileTreeCacheContext(t *testing.T) (*cacheContext, []byte, digest.Digest) {
	t.Helper()
	cc := &cacheContext{tree: iradix.New[*CacheRecord](), dirtyMap: map[string]struct{}{}, linkMap: map[string][][]byte{}}
	for _, stat := range []*types.Stat{
		{Path: "alias", Mode: 0o644, Linkname: "nested/file"},
		{Path: "nested", Mode: uint32(os.ModeDir) | 0o755},
		{Path: "nested/file", Mode: 0o644},
		{Path: "link", Mode: uint32(os.ModeSymlink) | 0o777, Linkname: "nested/file"},
		{Path: "byte-\xff", Mode: 0o644},
	} {
		info := fileTreeTestInfo{StatInfo: &fsutil.StatInfo{Stat: stat}, hash: hashutil.HashStrings(stat.Path)}
		require.NoError(t, cc.HandleChange(fsutil.ChangeKindAdd, stat.Path, info, nil))
	}
	cc.commitActiveTransaction()
	txn := cc.tree.Txn()
	root, _, err := cc.checksum(t.Context(), txn.Root(), txn, &mount{}, nil, false)
	require.NoError(t, err)
	cc.tree = txn.Commit()
	data, err := MarshalCacheContext(cc)
	require.NoError(t, err)
	return cc, data, root.Digest
}

func TestFileTreeCacheContextRoundTrip(t *testing.T) {
	before, data, expected := testFileTreeCacheContext(t)
	after, err := unmarshalFileTreeCacheContext(t.Context(), nil, data, expected)
	require.NoError(t, err)
	for _, name := range []string{"/", "/nested", "/nested/file", "/alias", "/link", "/byte-\xff"} {
		for _, follow := range []bool{false, true} {
			opts := ChecksumOpts{FollowLinks: follow}
			want, err := before.Checksum(t.Context(), nil, name, opts)
			require.NoError(t, err)
			got, err := after.Checksum(t.Context(), nil, name, opts)
			require.NoError(t, err)
			require.Equal(t, want, got, "path %q", name)
		}
	}
	roundTrip, err := MarshalCacheContext(after)
	require.NoError(t, err)
	require.Equal(t, data, roundTrip, "retain the exact existing metadata encoding")
}

func TestFileTreeCacheContextRejectsInvalidRecords(t *testing.T) {
	_, data, expected := testFileTreeCacheContext(t)
	cases := map[string]func(*CacheRecords){
		"empty":          func(r *CacheRecords) { r.Paths = nil },
		"missing record": func(r *CacheRecords) { r.Paths[2].Record = nil },
		"duplicate":      func(r *CacheRecords) { r.Paths = append(r.Paths[:2], r.Paths[1:]...) },
		"unordered":      func(r *CacheRecords) { r.Paths[1], r.Paths[2] = r.Paths[2], r.Paths[1] },
		"relative path":  func(r *CacheRecords) { r.Paths[2].Path = "alias" },
		"unclean path":   func(r *CacheRecords) { r.Paths[2].Path = "\x00..\x00alias" },
		"unknown kind":   func(r *CacheRecords) { r.Paths[2].Record.Type = 99 },
		"empty digest":   func(r *CacheRecords) { r.Paths[2].Record.Digest = "" },
		"malformed XXH3": func(r *CacheRecords) { r.Paths[2].Record.Digest = "xxh3:wrong" },
		"uppercase XXH3": func(r *CacheRecords) { r.Paths[2].Record.Digest = "xxh3:AAAAAAAAAAAAAAAA" },
		"missing header": func(r *CacheRecords) { r.Paths = append(r.Paths[:1], r.Paths[2:]...) },
		"missing parent": func(r *CacheRecords) { r.Paths[2].Path = "\x00absent\x00alias" },
		"leaf mismatch":  func(r *CacheRecords) { r.Paths[2].Record.Digest = hashutil.HashStrings("different") },
		"root mismatch":  func(r *CacheRecords) { r.Paths[0].Record.Digest = digest.FromString("different") },
	}
	for name, change := range cases {
		t.Run(name, func(t *testing.T) {
			var records CacheRecords
			require.NoError(t, records.Unmarshal(data))
			change(&records)
			invalid, err := records.Marshal()
			require.NoError(t, err)
			_, err = unmarshalFileTreeCacheContext(t.Context(), nil, invalid, expected)
			require.Error(t, err)
		})
	}
	_, err := unmarshalFileTreeCacheContext(t.Context(), nil, []byte{0xff}, expected)
	require.Error(t, err)
	_, err = unmarshalFileTreeCacheContext(t.Context(), nil, data, digest.FromString("wrong expected root"))
	require.Error(t, err)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err = unmarshalFileTreeCacheContext(ctx, nil, data, expected)
	require.ErrorIs(t, err, context.Canceled)
}
