package filesync

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"

	"github.com/dagger/dagger/engine/wcprof"
	digest "github.com/opencontainers/go-digest"
)

// immutableFileSource uses the hashes already verified during synchronization.
// The cache is an accelerator, not an alternative representation of a result:
// committed snapshots own their hardlinks and do not depend on cache entries.
// There are no directory manifests, content-store transactions or parent layers.
func (local *localFS) immutableFileSource(ctx context.Context, changes []CachedChange) func(string, os.FileInfo) (string, error) {
	files := make(map[string]*HashedStatInfo, len(changes))
	for _, change := range changes {
		value := change.result()
		if value.stat != nil && value.stat.Mode().IsRegular() && value.stat.Linkname == "" {
			files[filepath.Join(local.rootPath, change.callKey)] = value.stat
		}
	}
	// Equal independent files must not become hardlink aliases within a result.
	// Actual source hardlink groups are handled first by layercopy itself.
	used := make(map[digest.Digest]struct{})
	return func(path string, info os.FileInfo) (string, error) {
		if err := context.Cause(ctx); err != nil {
			return "", err
		}
		stat := files[path]
		if stat == nil {
			return "", nil
		}
		// Semantic hashes intentionally omit mtime; shared inodes cannot. Size is
		// included as a cheap additional check. Mode/ownership are in the digest.
		key := digest.FromString(fmt.Sprintf("%s:%d:%d", stat.Digest(), stat.ModTime().UnixNano(), stat.Size()))
		if _, duplicate := used[key]; duplicate {
			return "", nil
		}
		used[key] = struct{}{}
		return cachedFile(ctx, local.blobRoot, key, path, stat)
	}
}

// cachedFile publishes complete, metadata-compatible inodes atomically. Files
// are never modified after publication. Losing the cache only causes a copy;
// unlinking its entry cannot invalidate a previously committed snapshot.
func cachedFile(ctx context.Context, root string, key digest.Digest, source string, stat *HashedStatInfo) (_ string, rerr error) {
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.filecache.lookup", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	name := key.Encoded()
	dir := filepath.Join(root, name[:2])
	path := filepath.Join(dir, name[2:])
	if info, err := os.Lstat(path); err == nil {
		owner, ok := info.Sys().(*syscall.Stat_t)
		if !ok || owner.Uid != stat.Uid || owner.Gid != stat.Gid || !info.Mode().IsRegular() || info.Size() != stat.Size() || info.Mode() != stat.Mode() || !info.ModTime().Equal(stat.ModTime()) {
			return "", fmt.Errorf("invalid filesync cache object %s", key)
		}
		return path, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	_, ingest := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.filecache.ingest", wcprof.OpOpts{})
	defer func() { ingest.EndErr(rerr) }()
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	f, err := os.CreateTemp(dir, ".ingest-")
	if err != nil {
		return "", err
	}
	defer os.Remove(f.Name())
	defer f.Close()
	src, err := os.Open(source)
	if err != nil {
		return "", err
	}
	defer src.Close()
	hash := newHashFromStat(stat.Stat)
	buf := copyBufferPool.Get().(*[]byte)
	n, err := io.CopyBuffer(io.MultiWriter(f, hash), src, *buf)
	copyBufferPool.Put(buf)
	if err != nil {
		return "", err
	}
	if n != stat.Size() || digest.NewDigest(stat.Digest().Algorithm(), hash) != stat.Digest() {
		return "", fmt.Errorf("filesync cache source changed while copying %q", source)
	}
	if err := f.Close(); err != nil {
		return "", err
	}
	if err := rewriteMetadata(f.Name(), stat.Stat); err != nil {
		return "", err
	}
	// Link is no-replace publication. Concurrent publishers of the same verified
	// object are equivalent. No fsync is needed for an engine-local cache entry.
	if err := os.Link(f.Name(), path); err != nil && !os.IsExist(err) {
		return "", err
	}
	return path, nil
}
