//go:build linux

package filetree

import (
	"bytes"
	"cmp"
	"context"
	"errors"
	"fmt"
	"io"
	"maps"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strings"

	"github.com/containerd/continuity/sysx"
	"golang.org/x/sys/unix"
)

// Materialize derives a filesystem view from retained content. destination must
// be an exclusively owned, merged mutable snapshot: either empty (before == nil)
// or a writable child of the immutable snapshot described by before. Never pass
// an overlay upperdir, a host source directory, or a concurrently mutated path.
// On failure the caller must discard the mutable snapshot, not publish it.
//
// Unchanged files are left in the snapshot parent; changed bytes come only from
// CAS. With no parent, the same operation reconstructs the complete tree. This
// does not hardlink content-store blobs into a writable filesystem.
func Materialize(ctx context.Context, destination string, before, after *View) (rerr error) {
	if after == nil {
		return errors.New("materialize filetree: missing destination tree")
	}
	if err := context.Cause(ctx); err != nil {
		return err
	}
	if before != nil && before.root == after.root {
		return nil
	}
	root, err := os.OpenRoot(destination)
	if err != nil {
		return err
	}
	defer func() { rerr = errors.Join(rerr, root.Close()) }()

	changed := make(map[string]bool)
	dirs := make(map[string]bool)
	for name, next := range after.entries {
		var previous *viewEntry
		if before != nil {
			previous = before.entries[name]
		}
		if !sameViewEntry(previous, next) {
			changed[name] = true
		}
	}
	// Adding an alias may copy up its lower-layer target. Rebuild that group
	// explicitly; overlay index/copy-up must not detach unchanged sibling aliases.
	for name, next := range after.entries {
		if next.kind == Hardlink && changed[name] {
			changed[next.stat.Linkname] = true
		}
	}
	// A hardlink can live in an unchanged subtree while its target is replaced.
	// Comparing only its own manifest would leave it attached to the old inode.
	for name, next := range after.entries {
		if next.kind == Hardlink && changed[next.stat.Linkname] {
			changed[name] = true
		}
	}
	markParents := func(name string) {
		for name != "." {
			name = path.Dir(name)
			if entry := after.entries[name]; entry != nil && entry.kind == Directory {
				dirs[name] = true
			}
		}
	}

	if before != nil {
		removedDirs := make(map[string]bool)
		for _, name := range before.paths {
			if err := context.Cause(ctx); err != nil {
				return err
			}
			removedParent := false
			for parent := path.Dir(name); parent != "."; parent = path.Dir(parent) {
				if removedDirs[parent] {
					removedParent = true
					break
				}
			}
			if removedParent {
				continue
			}
			previous, next := before.entries[name], after.entries[name]
			if next != nil && (!changed[name] || previous.kind == Directory && next.kind == Directory) {
				continue
			}
			if err := root.RemoveAll(name); err != nil {
				return fmt.Errorf("remove old filetree entry %q: %w", name, err)
			}
			markParents(name)
			if previous.kind == Directory {
				removedDirs[name] = true
			}
		}
	}

	for _, name := range after.paths {
		if err := context.Cause(ctx); err != nil {
			return err
		}
		if !changed[name] {
			continue
		}
		next := after.entries[name]
		markParents(name)
		switch next.kind {
		case Directory:
			if before == nil || before.entries[name] == nil || before.entries[name].kind != Directory {
				if err := root.Mkdir(name, 0o700); err != nil {
					return fmt.Errorf("create filetree directory %q: %w", name, err)
				}
			}
			dirs[name] = true
		case File:
			if err := materializeFile(ctx, root, name, after); err != nil {
				return fmt.Errorf("materialize file %q: %w", name, err)
			}
		case Symlink:
			if err := root.Symlink(next.stat.Linkname, name); err != nil {
				return fmt.Errorf("materialize symlink %q: %w", name, err)
			}
		case Hardlink:
			// All regular targets must exist before aliases, irrespective of
			// lexical order. NewView already checked the complete root graph.
			continue
		}
		if next.kind != Directory {
			if err := materializeMetadata(root, name, next); err != nil {
				return fmt.Errorf("materialize metadata %q: %w", name, err)
			}
		}
	}
	for _, name := range after.paths {
		if err := context.Cause(ctx); err != nil {
			return err
		}
		next := after.entries[name]
		if changed[name] && next.kind == Hardlink {
			if err := root.Link(next.stat.Linkname, name); err != nil {
				return fmt.Errorf("materialize hardlink %q: %w", name, err)
			}
		}
	}
	if changed["."] {
		dirs["."] = true
	}
	// Restore only directories affected by this delta, deepest first. Creating,
	// deleting, or linking children must not leak new mtimes into their ancestors.
	dirNames := slices.SortedFunc(maps.Keys(dirs), func(a, b string) int {
		if a == b {
			return 0
		}
		if a == "." {
			return 1
		}
		if b == "." {
			return -1
		}
		return cmp.Or(cmp.Compare(strings.Count(b, "/"), strings.Count(a, "/")), strings.Compare(a, b))
	})
	for _, name := range dirNames {
		if err := context.Cause(ctx); err != nil {
			return err
		}
		if err := materializeMetadata(root, name, after.entries[name]); err != nil {
			return fmt.Errorf("materialize directory metadata %q: %w", name, err)
		}
	}
	return nil
}

func sameViewEntry(a, b *viewEntry) bool {
	if a == nil || a.kind != b.kind || a.kind != Directory && a.object != b.object {
		return false
	}
	return a.stat.Mode == b.stat.Mode && a.stat.Uid == b.stat.Uid && a.stat.Gid == b.stat.Gid &&
		a.stat.ModTime == b.stat.ModTime && a.stat.Linkname == b.stat.Linkname &&
		maps.EqualFunc(a.stat.Xattrs, b.stat.Xattrs, bytes.Equal)
}

func materializeFile(ctx context.Context, root *os.Root, name string, view *View) (rerr error) {
	in, err := view.Open(name)
	if err != nil {
		return err
	}
	defer func() { rerr = errors.Join(rerr, in.Close()) }()
	out, err := root.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	defer func() { rerr = errors.Join(rerr, out.Close()) }()
	n, err := io.Copy(out, &contextReader{ctx: ctx, r: in})
	if err != nil {
		return err
	}
	if n != view.entries[name].object.Size {
		return fmt.Errorf("copied %d bytes, expected %d", n, view.entries[name].object.Size)
	}
	return nil
}

func materializeMetadata(root *os.Root, name string, entry *viewEntry) error {
	stat := &entry.stat
	if err := root.Lchown(name, int(stat.Uid), int(stat.Gid)); err != nil {
		return err
	}
	// Parents come from the validated tree and are directories. The destination
	// is exclusive, so these no-follow operations cannot race a parent swap.
	fullPath := filepath.Join(root.Name(), name)
	attrs, err := sysx.LListxattr(fullPath)
	if err != nil && !(errors.Is(err, unix.ENOTSUP) && len(stat.Xattrs) == 0) {
		return err
	}
	for _, key := range attrs {
		if _, keep := stat.Xattrs[key]; !keep {
			if err := sysx.LRemovexattr(fullPath, key); err != nil {
				return err
			}
		}
	}
	for key, value := range stat.Xattrs {
		if err := sysx.LSetxattr(fullPath, key, value, 0); err != nil {
			return err
		}
	}
	if entry.kind != Symlink {
		if err := root.Chmod(name, os.FileMode(stat.Mode)); err != nil {
			return err
		}
	}
	timestamp := unix.NsecToTimespec(stat.ModTime)
	return unix.UtimesNanoAt(unix.AT_FDCWD, fullPath, []unix.Timespec{timestamp, timestamp}, unix.AT_SYMLINK_NOFOLLOW)
}
