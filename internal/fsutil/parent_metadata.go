package fsutil

import (
	"context"
	"io"
	gofs "io/fs"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

// NewParentMetadataFS describes a literal directory chain, rather than a
// filtered directory enumeration. It obtains fresh metadata on every walk,
// does not enumerate siblings, and cannot serve file contents. A missing or
// non-directory component found during preflight fails before any records are
// emitted. A concurrent mutation during later stat emission can still fail a
// partially emitted stream, as in ordinary filesystem synchronization.
//
// Unlike glob matching over ReadDir entries, native path lookup applies the
// host filesystem's spelling/case rules. This is an explicit operation, never
// an implicit replacement for NewFilterFS. No filesystem-type gate is needed.
func NewParentMetadataFS(root, target string) (FS, error) {
	if !filepath.IsLocal(target) || target == "." || filepath.Clean(target) != target {
		return nil, &os.PathError{Op: "parent metadata target", Path: target, Err: syscall.EINVAL}
	}
	base, err := NewFS(root)
	if err != nil {
		return nil, err
	}
	return &parentMetadataFS{fs: base.(*fs), target: target}, nil
}

type parentMetadataFS struct {
	*fs
	target string
}

func (f *parentMetadataFS) Open(path string) (io.ReadCloser, error) {
	return nil, &os.PathError{Op: "open parent metadata", Path: path, Err: syscall.EISDIR}
}

func (f *parentMetadataFS) Walk(ctx context.Context, target string, fn gofs.WalkDirFunc) error {
	// fsutil.Send and filter wrappers use the protocol root "/" on every OS.
	if target != "" && target != "." && target != "/" && target != string(filepath.Separator) {
		return &os.PathError{Op: "walk parent metadata", Path: target, Err: syscall.EINVAL}
	}
	return f.walk(ctx, fn, os.Lstat)
}

func (f *parentMetadataFS) walk(ctx context.Context, fn gofs.WalkDirFunc, lstat func(string) (os.FileInfo, error)) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	rootInfo, err := lstat(f.root)
	if err != nil {
		return err
	}
	if !rootInfo.IsDir() {
		return &os.PathError{Op: "parent metadata root", Path: f.root, Err: syscall.ENOTDIR}
	}
	// Resolve the complete directory chain first. This preserves the delayed
	// parent emission of the prior filtered walk when the target disappeared,
	// and rejects files/symlinks without a partial chain or content stream.
	seenFiles := make(map[uint64]string)
	entries := make([]*DirEntryInfo, 0, strings.Count(f.target, string(filepath.Separator))+1)
	var rel string
	for _, component := range strings.Split(f.target, string(filepath.Separator)) {
		if err := ctx.Err(); err != nil {
			return err
		}
		rel = filepath.Join(rel, component)
		full := filepath.Join(f.root, rel)
		info, err := lstat(full)
		if err != nil {
			return err
		}
		if !info.IsDir() {
			return &os.PathError{Op: "parent directory metadata", Path: full, Err: syscall.ENOTDIR}
		}
		entries = append(entries, &DirEntryInfo{
			path: rel, origpath: full, seenFiles: seenFiles,
			entry: &parentMetadataEntry{path: full, info: info},
		})
	}
	for _, entry := range entries {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := fn(entry.path, entry, nil); err != nil {
			if err == filepath.SkipDir || err == filepath.SkipAll {
				return nil
			}
			return err
		}
	}
	return nil
}

// Keep emission-time metadata fresh, as ordinary fsutil DirEntryInfo does.
// A replacement with a file/symlink is an error, never a content request.
type parentMetadataEntry struct {
	path string
	info os.FileInfo
}

func (e *parentMetadataEntry) Name() string        { return e.info.Name() }
func (e *parentMetadataEntry) IsDir() bool         { return true }
func (e *parentMetadataEntry) Type() gofs.FileMode { return gofs.ModeDir }
func (e *parentMetadataEntry) Info() (os.FileInfo, error) {
	info, err := os.Lstat(e.path)
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return nil, &os.PathError{Op: "parent directory metadata", Path: e.path, Err: syscall.ENOTDIR}
	}
	return info, nil
}
