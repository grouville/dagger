package filetree

import (
	"bytes"
	"encoding/json"
	"reflect"
	"slices"
	"strings"
	"testing"

	"github.com/opencontainers/go-digest"
)

func testObject(value string) *Object {
	return &Object{Digest: digest.FromString(value), Size: int64(len(value))}
}

func testTree() Tree {
	return Tree{
		Version: TreeVersion,
		Metadata: Metadata{Mode: 0o755, Xattrs: []Xattr{
			{Name: []byte("user.z"), Value: []byte("z")},
			{Name: []byte("user.a"), Value: []byte("a")},
		}},
		Entries: []Entry{
			{Name: []byte("z"), Kind: Directory, Object: testObject("child tree")},
			{Name: []byte("a"), Kind: File, Object: testObject("data"), Metadata: &Metadata{
				Mode: 0o644, Xattrs: []Xattr{
					{Name: []byte("user.z"), Value: []byte("z")},
					{Name: []byte("user.a"), Value: []byte("a")},
				},
			}},
			{Name: []byte("s"), Kind: Symlink, Metadata: &Metadata{Mode: 0o777}, Linkname: []byte("/outside/../target")},
			{Name: []byte("h"), Kind: Hardlink, Linkname: []byte("z/file")},
		},
	}
}

func mustEncode(t *testing.T, tree Tree) []byte {
	t.Helper()
	data, err := Encode(tree)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestCanonicalPermutationAndNoMutation(t *testing.T) {
	original := testTree()
	before, err := json.Marshal(original)
	if err != nil {
		t.Fatal(err)
	}
	encoded := mustEncode(t, original)
	after, err := json.Marshal(original)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(before, after) {
		t.Fatal("Encode mutated its input")
	}
	permuted := testTree()
	slices.Reverse(permuted.Metadata.Xattrs)
	slices.Reverse(permuted.Entries[1].Metadata.Xattrs)
	slices.Reverse(permuted.Entries)
	if !bytes.Equal(encoded, mustEncode(t, permuted)) {
		t.Fatal("ordering changed canonical encoding")
	}
	decoded, err := Decode(encoded)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(encoded, mustEncode(t, decoded)) {
		t.Fatal("canonical round trip changed encoding")
	}
	if len(decoded.References()) != 2 {
		t.Fatal("unexpected direct references")
	}
}

func TestCanonicalEmptyValues(t *testing.T) {
	tree := Tree{Version: TreeVersion}
	if got := string(mustEncode(t, tree)); got != `{"version":1,"metadata":{"mode":0,"uid":0,"gid":0,"modTime":0},"entries":[]}` {
		t.Fatalf("unexpected empty encoding: %s", got)
	}
	tree.Metadata.Xattrs = []Xattr{{Name: []byte("user.empty")}}
	first := mustEncode(t, tree)
	tree.Metadata.Xattrs[0].Value = []byte{}
	if !bytes.Equal(first, mustEncode(t, tree)) {
		t.Fatal("nil and empty xattr values must encode identically")
	}
}

func TestMetadataAndBytesAffectIdentity(t *testing.T) {
	baseline := digest.FromBytes(mustEncode(t, testTree()))
	changes := map[string]func(*Tree){
		"root mode":       func(tree *Tree) { tree.Metadata.Mode ^= 1 },
		"root uid":        func(tree *Tree) { tree.Metadata.UID++ },
		"root gid":        func(tree *Tree) { tree.Metadata.GID++ },
		"root mtime":      func(tree *Tree) { tree.Metadata.ModTime-- },
		"xattr name":      func(tree *Tree) { tree.Metadata.Xattrs[0].Name = []byte("user.other") },
		"xattr value":     func(tree *Tree) { tree.Metadata.Xattrs[0].Value = []byte("other") },
		"file mode":       func(tree *Tree) { tree.Entries[1].Metadata.Mode ^= 1 },
		"name":            func(tree *Tree) { tree.Entries[1].Name = []byte("other") },
		"file bytes":      func(tree *Tree) { tree.Entries[1].Object = testObject("changed") },
		"child tree":      func(tree *Tree) { tree.Entries[0].Object = testObject("changed tree") },
		"symlink target":  func(tree *Tree) { tree.Entries[2].Linkname = []byte("relative") },
		"hardlink target": func(tree *Tree) { tree.Entries[3].Linkname = []byte("other/file") },
	}
	for name, change := range changes {
		t.Run(name, func(t *testing.T) {
			tree := testTree()
			change(&tree)
			if digest.FromBytes(mustEncode(t, tree)) == baseline {
				t.Fatal("changed metadata or bytes did not change storage identity")
			}
		})
	}
}

func TestNonUTF8RoundTrip(t *testing.T) {
	name, target, xattr := []byte{'f', 0xff}, []byte{'/', 0xfe}, []byte{'u', 0xfd}
	tree := Tree{Version: TreeVersion, Entries: []Entry{{
		Name: name, Kind: Symlink, Linkname: target,
		Metadata: &Metadata{Mode: 0o777, Xattrs: []Xattr{{Name: xattr, Value: []byte{0, 0xff}}}},
	}}}
	decoded, err := Decode(mustEncode(t, tree))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(decoded.Entries[0], tree.Entries[0]) {
		t.Fatalf("bytes changed: %#v", decoded.Entries[0])
	}
	// Backslashes are ordinary bytes in the portable '/'-separated format.
	tree.Entries = []Entry{{Name: []byte(`a\b`), Kind: Hardlink, Linkname: []byte{'d', '/', 0xff}}}
	if _, err := Decode(mustEncode(t, tree)); err != nil {
		t.Fatal(err)
	}
}

func TestInvalidObjects(t *testing.T) {
	for _, object := range []Object{
		{},
		{Digest: "sha256:bad", Size: 0},
		{Digest: digest.Digest("sha256:" + strings.Repeat("A", 64))},
		{Digest: digest.Digest("sha512:" + strings.Repeat("a", 128))},
		{Digest: digest.FromString("file"), Size: -1},
	} {
		if err := object.Validate(); err == nil {
			t.Errorf("accepted invalid object %#v", object)
		}
		tree := Tree{Version: TreeVersion, Entries: []Entry{{Name: []byte("f"), Kind: File, Metadata: &Metadata{}, Object: &object}}}
		if _, err := Encode(tree); err == nil {
			t.Errorf("encoded invalid object %#v", object)
		}
	}
	if err := testObject("").Validate(); err != nil {
		t.Fatal(err)
	}
}

func TestInvalidTrees(t *testing.T) {
	changes := map[string]func(*Tree){
		"version":              func(tree *Tree) { tree.Version++ },
		"root filetype":        func(tree *Tree) { tree.Metadata.Mode = 0o100644 },
		"entry filetype":       func(tree *Tree) { tree.Entries[1].Metadata.Mode = 0o100644 },
		"duplicate entry":      func(tree *Tree) { tree.Entries = append(tree.Entries, tree.Entries[0]) },
		"duplicate root xattr": func(tree *Tree) { tree.Metadata.Xattrs = append(tree.Metadata.Xattrs, tree.Metadata.Xattrs[0]) },
		"duplicate file xattr": func(tree *Tree) {
			tree.Entries[1].Metadata.Xattrs = append(tree.Entries[1].Metadata.Xattrs, tree.Entries[1].Metadata.Xattrs[0])
		},
		"empty xattr":         func(tree *Tree) { tree.Metadata.Xattrs[0].Name = nil },
		"NUL xattr":           func(tree *Tree) { tree.Metadata.Xattrs[0].Name = []byte{'a', 0} },
		"unknown kind":        func(tree *Tree) { tree.Entries[0].Kind = "fifo" },
		"directory metadata":  func(tree *Tree) { tree.Entries[0].Metadata = &Metadata{} },
		"directory no object": func(tree *Tree) { tree.Entries[0].Object = nil },
		"directory target":    func(tree *Tree) { tree.Entries[0].Linkname = []byte("target") },
		"file no metadata":    func(tree *Tree) { tree.Entries[1].Metadata = nil },
		"file no object":      func(tree *Tree) { tree.Entries[1].Object = nil },
		"file target":         func(tree *Tree) { tree.Entries[1].Linkname = []byte("target") },
		"symlink no metadata": func(tree *Tree) { tree.Entries[2].Metadata = nil },
		"symlink object":      func(tree *Tree) { tree.Entries[2].Object = testObject("wrong") },
		"symlink no target":   func(tree *Tree) { tree.Entries[2].Linkname = nil },
		"symlink NUL":         func(tree *Tree) { tree.Entries[2].Linkname = []byte{'a', 0} },
		"hardlink metadata":   func(tree *Tree) { tree.Entries[3].Metadata = &Metadata{} },
		"hardlink object":     func(tree *Tree) { tree.Entries[3].Object = testObject("wrong") },
	}
	for _, invalid := range []string{"", ".", "..", "/a", "a/b", "a\x00b"} {
		changes["name "+invalid] = func(tree *Tree) { tree.Entries[0].Name = []byte(invalid) }
	}
	for _, invalid := range []string{"", ".", "..", "/a", "a/", "a//b", "a/./b", "a/../b", "a\x00b"} {
		changes["hardlink "+invalid] = func(tree *Tree) { tree.Entries[3].Linkname = []byte(invalid) }
	}
	for name, change := range changes {
		t.Run(name, func(t *testing.T) {
			tree := testTree()
			change(&tree)
			if _, err := Encode(tree); err == nil {
				t.Fatal("accepted invalid tree")
			}
		})
	}
}

func TestReferencesAndConflictingSizes(t *testing.T) {
	tree := testTree()
	copy := *tree.Entries[1].Object
	tree.Entries = append(tree.Entries, Entry{Name: []byte("duplicate-content"), Kind: File, Metadata: &Metadata{}, Object: &copy})
	mustEncode(t, tree)
	refs := tree.References()
	if len(refs) != 2 || refs[0].Digest >= refs[1].Digest {
		t.Fatalf("references not deduplicated and sorted: %#v", refs)
	}
	copy.Size++
	if _, err := Encode(tree); err == nil {
		t.Fatal("accepted conflicting child object sizes")
	}
	raw, err := json.Marshal(tree)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Decode(raw); err == nil {
		t.Fatal("decoded conflicting child object sizes")
	}
}

func TestRejectNoncanonicalJSON(t *testing.T) {
	data := mustEncode(t, Tree{Version: TreeVersion})
	invalid := [][]byte{
		[]byte(`null`),
		append(bytes.Clone(data), '\n'),
		append(bytes.Clone(data), []byte(`{}`)...),
		append(bytes.Clone(data), []byte(`invalid`)...),
		bytes.Replace(data, []byte(`"version":1`), []byte(`"version":1,"unknown":true`), 1),
		bytes.Replace(data, []byte(`"version":1`), []byte(`"version":1,"version":1`), 1),
		bytes.Replace(data, []byte(`"mode":0`), []byte(`"mode":0,"unknown":true`), 1),
		bytes.Replace(data, []byte(`"mode":0`), []byte(`"mode":0,"mode":0`), 1),
		bytes.Replace(data, []byte(`"entries":[]`), []byte(`"entries":null`), 1),
		bytes.Replace(data, []byte(`"uid":0,"gid":0`), []byte(`"gid":0,"uid":0`), 1),
		bytes.Replace(data, []byte(`"uid":0,`), nil, 1),
		bytes.Replace(data, []byte(`"version":1`), []byte(`"version":2`), 1),
	}
	unsorted, err := json.Marshal(testTree())
	if err != nil {
		t.Fatal(err)
	}
	invalid = append(invalid, unsorted)
	full := mustEncode(t, testTree())
	invalid = append(invalid,
		bytes.Replace(full, []byte(`"kind":"file"`), []byte(`"kind":"file","unknown":true`), 1),
		bytes.Replace(full, []byte(`"kind":"file"`), []byte(`"kind":"file","linkname":""`), 1),
	)
	for i, raw := range invalid {
		if _, err := Decode(raw); err == nil {
			t.Errorf("accepted invalid JSON case %d: %s", i, raw)
		}
	}
}
