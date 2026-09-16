package filesync

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"

	"github.com/dagger/dagger/engine/wcprof"
	digest "github.com/opencontainers/go-digest"
	"golang.org/x/sys/unix"
)

type fileCacheCandidate struct {
	key  digest.Digest
	stat *HashedStatInfo
	path string
}

// fileCacheCopy retains verified inodes built directly in a private result.
// The caller must finish the entire copy and stop all writers before publish,
// while both the result and cache mounts are still held.
type fileCacheCopy struct {
	ctx           context.Context
	root          string
	files         map[string]*HashedStatInfo
	used          map[digest.Digest]struct{}
	pendingSource string
	pending       fileCacheCandidate
	candidates    []fileCacheCandidate
}

func (local *localFS) newFileCacheCopy(ctx context.Context, changes []CachedChange) *fileCacheCopy {
	c := &fileCacheCopy{
		ctx:   ctx,
		root:  local.blobRoot,
		files: make(map[string]*HashedStatInfo, len(changes)),
		used:  make(map[digest.Digest]struct{}),
	}
	for _, change := range changes {
		value := change.result()
		if value.stat != nil && value.stat.Mode().IsRegular() && value.stat.Linkname == "" {
			c.files[filepath.Join(local.rootPath, change.callKey)] = value.stat
		}
	}
	return c
}

func fileCacheKey(stat *HashedStatInfo) digest.Digest {
	// Semantic hashes omit mtime, but shared inodes cannot. Mode and ownership
	// are already part of the digest; size is a cheap additional check.
	return digest.FromString(fmt.Sprintf("%s:%d:%d", stat.Digest(), stat.ModTime().UnixNano(), stat.Size()))
}

func fileCachePath(root string, key digest.Digest) string {
	name := key.Encoded()
	return filepath.Join(root, name[:2], name[2:])
}

func lookupCachedFile(path string, key digest.Digest, stat *HashedStatInfo) (string, error) {
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != stat.Uid || owner.Gid != stat.Gid || !info.Mode().IsRegular() || info.Size() != stat.Size() || info.Mode() != stat.Mode() || !info.ModTime().Equal(stat.ModTime()) {
		return "", fmt.Errorf("invalid filesync cache object %s", key)
	}
	return path, nil
}

func (c *fileCacheCopy) lookup(source string, _ os.FileInfo) (_ string, rerr error) {
	_, op := wcprof.BeginOp(c.ctx, wcprof.OpKindIO, "filesync.filecache.lookup", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	c.pendingSource = ""
	if err := context.Cause(c.ctx); err != nil {
		return "", err
	}
	stat := c.files[source]
	if stat == nil {
		return "", nil
	}
	key := fileCacheKey(stat)
	// Only the first independent file may reuse or populate this cache key.
	// Genuine source hardlink aliases are handled by layercopy before lookup.
	if _, duplicate := c.used[key]; duplicate {
		return "", nil
	}
	c.used[key] = struct{}{}
	c.pendingSource = source
	c.pending = fileCacheCandidate{key: key, stat: stat}
	return lookupCachedFile(fileCachePath(c.root, key), key, stat)
}

func (c *fileCacheCopy) materialize(source, destination string, _ os.FileInfo) (_ bool, rerr error) {
	if c.pendingSource != source {
		return false, nil
	}
	c.pendingSource = ""
	candidate := c.pending
	_, op := wcprof.BeginOp(c.ctx, wcprof.OpKindIO, "filesync.filecache.ingest", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	if err := context.Cause(c.ctx); err != nil {
		return false, err
	}
	// CopyToEmpty guarantees a fresh private path; never truncate an alias.
	f, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return false, err
	}
	defer f.Close()
	defer func() {
		if rerr != nil {
			_ = os.Remove(destination)
		}
	}()
	if err := writeCachedFile(f, source, candidate.stat); err != nil {
		return false, err
	}
	candidate.path = destination
	c.candidates = append(c.candidates, candidate)
	return true, nil
}

func (c *fileCacheCopy) publish(ctx context.Context) (rerr error) {
	if len(c.candidates) == 0 {
		return nil
	}
	_, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.filecache.publish", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	for _, candidate := range c.candidates {
		if err := context.Cause(ctx); err != nil {
			return err
		}
		path := fileCachePath(c.root, candidate.key)
		if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
			return err
		}
		// No-replace publication cannot disturb a concurrent winner. A cache
		// link is optional when the snapshot filesystem cannot share this inode.
		if err := os.Link(candidate.path, path); err != nil && !os.IsExist(err) && !errors.Is(err, unix.EXDEV) && !errors.Is(err, unix.EMLINK) {
			return err
		}
	}
	c.candidates = nil
	return nil
}

// writeCachedFile verifies the actual destination bytes against the synchronized
// digest, then finalizes metadata. Mirror-only xattrs are never copied.
func writeCachedFile(f *os.File, source string, stat *HashedStatInfo) error {
	src, err := os.Open(source)
	if err != nil {
		return err
	}
	defer src.Close()
	hash := newHashFromStat(stat.Stat)
	buf := copyBufferPool.Get().(*[]byte)
	n, err := io.CopyBuffer(io.MultiWriter(f, hash), src, *buf)
	copyBufferPool.Put(buf)
	if err != nil {
		return err
	}
	if n != stat.Size() || digest.NewDigest(stat.Digest().Algorithm(), hash) != stat.Digest() {
		return fmt.Errorf("filesync cache source changed while copying %q", source)
	}
	if err := f.Close(); err != nil {
		return err
	}
	return rewriteMetadata(f.Name(), stat.Stat)
}
