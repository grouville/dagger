package filetree

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"io/fs"
	"os"
	"slices"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/internal/fsutil/types"
)

// View exposes a retained CAS tree without accessing a source filesystem or
// following symlinks. The caller must retain the root for the view's lifetime.
// Construction indexes every path, but reads each distinct directory object
// only once and never reads file payloads. This is not yet a Merkle-pruned walk.
type View struct {
	ctx     context.Context
	store   *Store
	root    Object
	entries map[string]*viewEntry
	paths   []string
}

type viewEntry struct {
	kind     Kind
	object   Object
	stat     types.Stat
	children []string
}

var _ fsutil.FS = (*View)(nil)

func NewView(ctx context.Context, store *Store, root Object) (*View, error) {
	if err := context.Cause(ctx); err != nil {
		return nil, err
	}
	if store == nil {
		return nil, fmt.Errorf("filetree view requires a store")
	}
	v := &View{ctx: ctx, store: store, root: root, entries: make(map[string]*viewEntry)}
	type directory struct {
		path   string
		object Object
	}
	pending := []directory{{path: ".", object: root}}
	trees := make(map[Object]Tree)
	for len(pending) > 0 {
		if err := context.Cause(ctx); err != nil {
			return nil, err
		}
		dir := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		tree, ok := trees[dir.object]
		if !ok {
			var err error
			tree, err = store.ReadTree(ctx, dir.object)
			if err != nil {
				return nil, fmt.Errorf("read tree at %q: %w", dir.path, err)
			}
			trees[dir.object] = tree
		}
		node := &viewEntry{kind: Directory, object: dir.object, stat: viewStat(dir.path, tree.Metadata)}
		node.stat.Mode |= uint32(os.ModeDir)
		v.entries[dir.path] = node
		for _, entry := range tree.Entries {
			if err := context.Cause(ctx); err != nil {
				return nil, err
			}
			name := string(entry.Name)
			if dir.path != "." {
				name = dir.path + "/" + name
			}
			node.children = append(node.children, name)
			v.paths = append(v.paths, name)
			if entry.Kind == Directory {
				pending = append(pending, directory{path: name, object: *entry.Object})
				continue
			}
			child := &viewEntry{kind: entry.Kind, stat: types.Stat{Path: name}}
			if entry.Metadata != nil {
				child.stat = viewStat(name, *entry.Metadata)
			}
			switch entry.Kind {
			case File:
				child.object = *entry.Object
				child.stat.Size_ = entry.Object.Size
			case Symlink:
				child.stat.Mode |= uint32(os.ModeSymlink)
				child.stat.Size_ = int64(len(entry.Linkname))
				child.stat.Linkname = string(entry.Linkname)
			case Hardlink:
				child.stat.Linkname = string(entry.Linkname)
			}
			v.entries[name] = child
		}
	}
	slices.Sort(v.paths)
	for _, name := range v.paths {
		if err := context.Cause(ctx); err != nil {
			return nil, err
		}
		entry := v.entries[name]
		if entry.kind != Hardlink {
			continue
		}
		target, ok := v.entries[entry.stat.Linkname]
		if !ok || target.kind != File {
			return nil, fmt.Errorf("hardlink %q must target a regular file directly: %q", name, entry.stat.Linkname)
		}
		linkname := entry.stat.Linkname
		entry.object = target.object
		entry.stat = cloneViewStat(target.stat)
		entry.stat.Path = name
		entry.stat.Linkname = linkname
	}
	return v, nil
}

func (v *View) Root() Object { return v.root }

// Entries returns all non-root paths, sorted by raw bytes, without exposing the
// index for mutation. Hardlinks can depend on files in otherwise unchanged trees.
func (v *View) Entries() []string { return slices.Clone(v.paths) }

func (v *View) Stat(name string) (*fsutil.StatInfo, error) {
	entry, err := v.lookup(name, "stat")
	if err != nil {
		return nil, err
	}
	stat := cloneViewStat(entry.stat)
	return &fsutil.StatInfo{Stat: &stat}, nil
}

func (v *View) Open(name string) (io.ReadCloser, error) {
	if err := context.Cause(v.ctx); err != nil {
		return nil, err
	}
	entry, err := v.lookup(name, "open")
	if err != nil {
		return nil, err
	}
	if entry.kind != File && entry.kind != Hardlink {
		return nil, &fs.PathError{Op: "open", Path: name, Err: fmt.Errorf("not a regular file: %w", fs.ErrInvalid)}
	}
	r, err := v.store.OpenFile(v.ctx, entry.object)
	if err != nil {
		return nil, err
	}
	return &struct {
		io.Reader
		io.Closer
	}{&contextReader{ctx: v.ctx, r: content.NewReader(r)}, r}, nil
}

// Walk follows WalkDir's lexical sibling order and skip semantics. As with
// fsutil.FS, walking the root omits the root callback itself.
func (v *View) Walk(ctx context.Context, target string, fn fs.WalkDirFunc) error {
	if err := context.Cause(ctx); err != nil {
		return err
	}
	entry, err := v.lookup(target, "walk")
	if err != nil {
		if !os.IsNotExist(err) {
			return err
		}
		err = fn(target, nil, err)
	} else {
		var walk func(*viewEntry, bool) error
		walk = func(entry *viewEntry, root bool) error {
			if err := context.Cause(ctx); err != nil {
				return err
			}
			if !root {
				stat := cloneViewStat(entry.stat)
				if err := fn(stat.Path, &fsutil.DirEntryInfo{Stat: &stat}, nil); err != nil {
					if err == fs.SkipDir && entry.kind == Directory {
						return nil
					}
					return err
				}
			}
			for _, name := range entry.children {
				if err := walk(v.entries[name], false); err != nil {
					if err == fs.SkipDir {
						break
					}
					return err
				}
			}
			return nil
		}
		err = walk(entry, entry.stat.Path == ".")
	}
	if err == fs.SkipDir || err == fs.SkipAll {
		return nil
	}
	return err
}

func (v *View) lookup(name, op string) (*viewEntry, error) {
	input := name
	switch name {
	case "", ".", "/":
		name = "."
	default:
		if !validHardlink([]byte(name)) {
			return nil, &fs.PathError{Op: op, Path: input, Err: fs.ErrInvalid}
		}
	}
	entry, ok := v.entries[name]
	if !ok {
		return nil, &fs.PathError{Op: op, Path: input, Err: fs.ErrNotExist}
	}
	return entry, nil
}

func viewStat(name string, metadata Metadata) types.Stat {
	mode := os.FileMode(metadata.Mode & 0o777)
	for _, bit := range []struct {
		posix uint32
		goBit os.FileMode
	}{{0o4000, os.ModeSetuid}, {0o2000, os.ModeSetgid}, {0o1000, os.ModeSticky}} {
		if metadata.Mode&bit.posix != 0 {
			mode |= bit.goBit
		}
	}
	stat := types.Stat{Path: name, Mode: uint32(mode), Uid: metadata.UID, Gid: metadata.GID, ModTime: metadata.ModTime}
	if len(metadata.Xattrs) > 0 {
		stat.Xattrs = make(map[string][]byte, len(metadata.Xattrs))
		for _, xattr := range metadata.Xattrs {
			stat.Xattrs[string(xattr.Name)] = bytes.Clone(xattr.Value)
		}
	}
	return stat
}

func cloneViewStat(stat types.Stat) types.Stat {
	if stat.Xattrs != nil {
		clone := make(map[string][]byte, len(stat.Xattrs))
		for key, value := range stat.Xattrs {
			clone[key] = bytes.Clone(value)
		}
		stat.Xattrs = clone
	}
	return stat
}
