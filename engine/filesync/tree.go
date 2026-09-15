package filesync

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strings"
	"syscall"

	"github.com/containerd/continuity/sysx"
	"github.com/containerd/errdefs"
	bkcontenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/filetree"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/opencontainers/go-digest"
)

// This is an engine-owned mirror hint, never a client-supplied content hash.
// Mirror writes replace regular inodes, invalidating their previous hint. A
// collected blob is re-ingested from the conflict-held mirror before publication.
const fileTreeObjectXattr = "user.daggerFileTreeObject.v1"

func (local *localFS) SyncTree(ctx context.Context, remote ReadFS, cacheManager bkcache.Accessor) (_ *filetree.Object, _ digest.Digest, rerr error) {
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.cas.sync", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	manager, ok := cacheManager.(bkcache.FileTreeManager)
	if !ok {
		return nil, "", errors.New("filesync requires content-addressed tree support")
	}
	in, err := manager.FileTreeIngest(ctx)
	if err != nil {
		return nil, "", err
	}
	var root filetree.Object
	_, dgst, err := local.sync(ctx, remote, cacheManager, false, func(ctx context.Context, changes []CachedChange, only map[string]struct{}, dgst digest.Digest) error {
		// Preserve filesync's existing semantic-equivalence reuse, which ignores
		// e.g. hardlink topology. Reuse the old CAS root, not merely its view:
		// reconstructing after view GC must give the same selected filesystem.
		cached, err := findTreeByContentHash(ctx, cacheManager, manager, dgst)
		if err != nil {
			return err
		}
		if cached != nil {
			root = *cached
			return nil
		}
		ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.cas.ingest", wcprof.OpOpts{})
		var ingestErr error
		root, ingestErr = local.ingestTree(ctx, in, changes, only)
		op.EndErr(ingestErr)
		return ingestErr
	})
	if err != nil {
		return nil, "", err
	}
	return &root, dgst, nil
}

func findTreeByContentHash(ctx context.Context, cacheManager bkcache.Accessor, manager bkcache.FileTreeManager, dgst digest.Digest) (_ *filetree.Object, rerr error) {
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.cas.lookup", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	matches, err := bkcontenthash.SearchContentHash(ctx, cacheManager, dgst)
	if err != nil {
		return nil, err
	}
	for _, match := range matches {
		root, err := manager.FileTreeRoot(ctx, match.SnapshotID())
		if err == nil {
			return &root, nil
		}
		if !bkcache.IsNotFound(err) && !errdefs.IsNotFound(err) {
			return nil, err
		}
	}
	return nil, nil
}

// ingestTree consumes the already-filtered sync result. It never walks the
// mirror, which can contain files from other imports or gitignored build output.
func (local *localFS) ingestTree(ctx context.Context, in *filetree.Ingest, changes []CachedChange, only map[string]struct{}) (filetree.Object, error) {
	base := cleanLocalCopyPath(local.copyPath)
	selected := localCopyOnlyPaths(only, base)
	stats := make(map[string]*types.Stat)
	for _, change := range changes {
		applied := change.result()
		if applied.kind == ChangeKindDelete || applied.stat == nil {
			continue
		}
		// A cached change can have been produced by an overlapping import with
		// a different subdir. Its Stat.Path belongs to that import, not ours.
		rel, err := filepath.Rel(filepath.Clean(local.subdir), change.callKey)
		if err != nil || !filepath.IsLocal(rel) {
			return filetree.Object{}, fmt.Errorf("filesync change %q is outside %q", change.callKey, local.subdir)
		}
		name := cleanLocalCopyPath(rel)
		if base != "" {
			if name == base {
				name = ""
			} else {
				var inside bool
				name, inside = strings.CutPrefix(name, base+"/")
				if !inside {
					continue
				}
			}
		}
		if _, keep := selected[name]; keep {
			stats[name] = applied.stat.Stat
		}
	}
	// Re-included descendants need ignored ancestors, but not those ancestors'
	// ignored siblings. Stat only those missing parents, never enumerate children.
	for name := range stats {
		for name != "" {
			name = path.Dir(name)
			if name == "." {
				name = ""
			}
			if _, ok := stats[name]; !ok {
				stat, err := fsutil.Stat(local.toFullPath(path.Join(base, name)))
				if err != nil {
					return filetree.Object{}, err
				}
				stats[name] = stat
			}
		}
	}
	if stats[""] == nil {
		stat, err := fsutil.Stat(local.toFullPath(base))
		if err != nil {
			return filetree.Object{}, err
		}
		stats[""] = stat
	}
	if os.FileMode(stats[""].Mode)&os.ModeDir == 0 {
		return filetree.Object{}, errors.New("filesync tree root is not a directory")
	}
	trees := make(map[string]*filetree.Tree)
	var names []string
	for name, stat := range stats {
		names = append(names, name)
		if os.FileMode(stat.Mode).IsDir() {
			trees[name] = &filetree.Tree{Version: filetree.TreeVersion, Metadata: treeMetadata(stat)}
		}
	}
	slices.Sort(names)
	type inodeKey struct{ device, inode uint64 }
	links := make(map[inodeKey]string)
	for _, name := range names {
		if err := context.Cause(ctx); err != nil {
			return filetree.Object{}, err
		}
		if name == "" || trees[name] != nil {
			continue
		}
		stat := stats[name]
		md := treeMetadata(stat)
		entry := filetree.Entry{Name: []byte(path.Base(name)), Metadata: &md}
		switch mode := os.FileMode(stat.Mode); {
		case mode&os.ModeSymlink != 0:
			entry.Kind = filetree.Symlink
			entry.Linkname = []byte(stat.Linkname)
		case mode.IsRegular():
			// Preserve internal groups without linking the mutable mirror into
			// results. Protocol Linkname can refer outside this filter or use a
			// different import's path base; the held mirror inode is definitive.
			info, err := os.Lstat(local.toFullPath(path.Join(base, name)))
			if err != nil {
				return filetree.Object{}, err
			}
			if !info.Mode().IsRegular() {
				return filetree.Object{}, fmt.Errorf("filesync entry %q is no longer a regular file", name)
			}
			unixStat := info.Sys().(*syscall.Stat_t)
			if unixStat.Nlink > 1 {
				key := inodeKey{uint64(unixStat.Dev), unixStat.Ino}
				if target, ok := links[key]; ok {
					entry.Kind, entry.Linkname, entry.Metadata = filetree.Hardlink, []byte(target), nil
				} else {
					links[key] = name
				}
			}
			if entry.Kind != filetree.Hardlink {
				obj, err := local.ingestFile(in, path.Join(base, name), stat.Size_)
				if err != nil {
					return filetree.Object{}, err
				}
				entry.Kind, entry.Object = filetree.File, &obj
			}
		default:
			return filetree.Object{}, fmt.Errorf("unsupported filesync entry %q: %s", name, mode)
		}
		parent := path.Dir(name)
		if parent == "." {
			parent = ""
		}
		if trees[parent] == nil {
			return filetree.Object{}, fmt.Errorf("missing directory for filesync entry %q", name)
		}
		trees[parent].Entries = append(trees[parent].Entries, entry)
	}
	// Every child sorts after its parent, including byte-valued filenames.
	for _, name := range slices.Backward(names) {
		tree := trees[name]
		if tree == nil {
			continue
		}
		obj, err := in.PutTree(*tree)
		if err != nil {
			return filetree.Object{}, err
		}
		if name == "" {
			return obj, nil
		}
		parent := path.Dir(name)
		if parent == "." {
			parent = ""
		}
		trees[parent].Entries = append(trees[parent].Entries, filetree.Entry{Name: []byte(path.Base(name)), Kind: filetree.Directory, Object: &obj})
	}
	return filetree.Object{}, errors.New("filesync tree has no root")
}

func (local *localFS) ingestFile(in *filetree.Ingest, name string, size int64) (filetree.Object, error) {
	fullPath := local.toFullPath(name)
	payload, err := sysx.Getxattr(fullPath, fileTreeObjectXattr)
	if err == nil {
		var obj filetree.Object
		if err := json.Unmarshal(payload, &obj); err != nil {
			return filetree.Object{}, fmt.Errorf("decode mirror filetree object %q: %w", name, err)
		}
		if obj.Size != size {
			return filetree.Object{}, fmt.Errorf("mirror filetree size mismatch for %q", name)
		}
		if err := in.Retain(obj); err == nil {
			return obj, nil
		} else if !errdefs.IsNotFound(err) {
			return filetree.Object{}, err
		}
	} else if !isMissingContentHashXattr(err) {
		return filetree.Object{}, err
	}
	f, err := os.Open(fullPath)
	if err != nil {
		return filetree.Object{}, err
	}
	obj, ingestErr := in.PutFile(f, size)
	if err := errors.Join(ingestErr, f.Close()); err != nil {
		return filetree.Object{}, err
	}
	payload, err = json.Marshal(obj)
	if err != nil {
		return filetree.Object{}, err
	}
	if err := sysx.Setxattr(fullPath, fileTreeObjectXattr, payload, 0); err != nil {
		return filetree.Object{}, err
	}
	return obj, nil
}

func treeMetadata(stat *types.Stat) filetree.Metadata {
	mode := os.FileMode(stat.Mode)
	bits := uint32(mode.Perm())
	if mode&os.ModeSetuid != 0 {
		bits |= 0o4000
	}
	if mode&os.ModeSetgid != 0 {
		bits |= 0o2000
	}
	if mode&os.ModeSticky != 0 {
		bits |= 0o1000
	}
	// Existing filesync deliberately does not publish xattrs. In particular,
	// engine-owned mirror hash hints must not become user-visible output.
	return filetree.Metadata{Mode: bits, UID: stat.Uid, GID: stat.Gid, ModTime: stat.ModTime}
}
