package contenthash

import (
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/dagger/dagger/engine/filetree"
	cache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/util/hashutil"
	iradix "github.com/hashicorp/go-immutable-radix/v2"
	"github.com/opencontainers/go-digest"
)

// Bound engine-authored checksum sidecars before allocating or decoding them.
// The sidecar contains path records, never file payloads.
const maxFileTreeChecksumsSize = 64 << 20

// MarshalCacheContext uses the same path-record encoding as snapshot metadata.
// Keeping these records with a CAS root preserves the original filesync hashes
// after its disposable snapshot and checksum metadata have been collected.
func MarshalCacheContext(cci CacheContext) ([]byte, error) {
	cc, ok := cci.(*cacheContext)
	if !ok {
		return nil, fmt.Errorf("invalid cache context: %T", cci)
	}
	cc.mu.Lock()
	defer cc.mu.Unlock()
	data, err := cc.marshalLocked()
	if err != nil {
		return nil, err
	}
	if len(data) > maxFileTreeChecksumsSize {
		return nil, errors.New("filetree checksum context exceeds size limit")
	}
	return data, nil
}

// RestoreFileTreeCacheContext restores exact filesync path hashes before a
// derived view is exposed. The caller must retain root for the entire operation.
// Trees without this optional engine-authored sidecar keep ordinary scan-based
// checksums. This package, rather than snapshots, bridges CAS and contenthash to
// avoid a dependency cycle.
func RestoreFileTreeCacheContext(ctx context.Context, blobs content.Store, root filetree.Object, md cache.RefMetadata, expected digest.Digest) error {
	if err := context.Cause(ctx); err != nil {
		return err
	}
	if blobs == nil {
		return errors.New("restore filetree checksums: missing content store")
	}
	store := filetree.NewStore(blobs)
	tree, err := store.ReadTree(ctx, root)
	if err != nil {
		return err
	}
	if tree.Checksums == nil {
		return nil
	}
	obj := *tree.Checksums
	if obj.Size > maxFileTreeChecksumsSize {
		return errors.New("filetree checksum context exceeds size limit")
	}
	r, err := store.OpenFile(ctx, obj)
	if err != nil {
		return err
	}
	data, readErr := io.ReadAll(io.LimitReader(content.NewReader(r), obj.Size+1))
	if err := errors.Join(readErr, r.Close()); err != nil {
		return err
	}
	if int64(len(data)) != obj.Size || digest.FromBytes(data) != obj.Digest {
		return errors.New("filetree checksum object digest or size mismatch")
	}
	cc, err := unmarshalFileTreeCacheContext(ctx, md, data, expected)
	if err != nil {
		return err
	}
	return SetCacheContext(ctx, md, cc)
}

// A complete context must never fall back to scanning the filesystem. Validate
// its structure and recompute recursive directory hashes using the existing
// checksum implementation before persisting it or publishing it in the LRU.
func unmarshalFileTreeCacheContext(ctx context.Context, md cache.RefMetadata, data []byte, expected digest.Digest) (*cacheContext, error) {
	if len(data) > maxFileTreeChecksumsSize {
		return nil, errors.New("filetree checksum context exceeds size limit")
	}
	var records CacheRecords
	if err := records.Unmarshal(data); err != nil {
		return nil, fmt.Errorf("decode filetree checksums: %w", err)
	}
	cc := &cacheContext{md: cacheMetadata{md}, tree: iradix.New[*CacheRecord](), dirtyMap: map[string]struct{}{}, linkMap: map[string][][]byte{}}
	txn := cc.tree.Txn()
	previous := ""
	for i, item := range records.Paths {
		if err := context.Cause(ctx); err != nil {
			return nil, err
		}
		if item == nil || item.Record == nil || (i > 0 && item.Path <= previous) {
			return nil, errors.New("invalid or unordered filetree checksum record")
		}
		previous = item.Path
		record := *item.Record
		if err := validateFileTreeChecksumRecord(item.Path, &record); err != nil {
			return nil, err
		}
		// Recursive values must agree with the retained leaf and header records,
		// not merely with a possibly stale root checksum copied into the sidecar.
		if record.Type == CacheRecordTypeDir {
			record.Digest = ""
		}
		txn.Insert([]byte(item.Path), &record)
	}
	root, ok := txn.Get(nil)
	if !ok || root.Type != CacheRecordTypeDir {
		return nil, errors.New("filetree checksum context has no root directory")
	}
	for _, item := range records.Paths {
		if err := context.Cause(ctx); err != nil {
			return nil, err
		}
		key := item.Path
		if item.Record.Type == CacheRecordTypeDir {
			header, ok := txn.Get([]byte(key + "\x00"))
			if !ok || header.Type != CacheRecordTypeDirHeader {
				return nil, fmt.Errorf("missing directory checksum header %q", key)
			}
		}
		if key == "" {
			continue
		}
		parent := key[:strings.LastIndexByte(key, 0)]
		dir, ok := txn.Get([]byte(parent))
		if !ok || dir.Type != CacheRecordTypeDir {
			return nil, fmt.Errorf("missing checksum parent directory for %q", key)
		}
	}
	cc.tree = txn.Commit()
	txn = cc.tree.Txn()
	computed, _, err := cc.checksum(ctx, txn.Root(), txn, &mount{}, nil, false)
	if err != nil {
		return nil, err
	}
	if computed.Digest != records.Paths[0].Record.Digest || (expected != "" && computed.Digest != expected) {
		return nil, fmt.Errorf("filetree root checksum mismatch: computed %s, recorded %s, expected %s", computed.Digest, records.Paths[0].Record.Digest, expected)
	}
	cc.tree = txn.Commit()
	return cc, nil
}

func validateFileTreeChecksumRecord(key string, record *CacheRecord) error {
	if strings.ContainsRune(key, '/') || (key != "" && key[0] != 0) {
		return fmt.Errorf("invalid checksum path %q", key)
	}
	if key != "" && key != "\x00" {
		name := strings.TrimSuffix(key[1:], "\x00")
		for _, part := range strings.Split(name, "\x00") {
			if part == "" || part == "." || part == ".." {
				return fmt.Errorf("invalid checksum path %q", key)
			}
		}
	}
	switch record.Type {
	case CacheRecordTypeDirHeader:
		if !strings.HasSuffix(key, "\x00") {
			return fmt.Errorf("invalid directory header path %q", key)
		}
	case CacheRecordTypeDir, CacheRecordTypeFile, CacheRecordTypeSymlink:
		if strings.HasSuffix(key, "\x00") || (key == "" && record.Type != CacheRecordTypeDir) {
			return fmt.Errorf("invalid checksum entry path %q", key)
		}
	default:
		return fmt.Errorf("invalid checksum record type %d", record.Type)
	}
	if strings.ContainsRune(record.Linkname, 0) || (record.Type != CacheRecordTypeSymlink && record.Linkname != "") {
		return fmt.Errorf("invalid checksum link at %q", key)
	}
	// Filesync's XXH3 is intentionally not registered as an OCI blob algorithm.
	// It is valid for semantic path hashes, never for CAS storage descriptors.
	if encoded, ok := strings.CutPrefix(record.Digest.String(), string(hashutil.XXH3)+":"); ok {
		if len(encoded) == 16 && strings.ToLower(encoded) == encoded {
			if _, err := hex.DecodeString(encoded); err == nil {
				return nil
			}
		}
		return fmt.Errorf("invalid XXH3 checksum at %q", key)
	}
	if err := record.Digest.Validate(); err != nil {
		return fmt.Errorf("invalid checksum at %q: %w", key, err)
	}
	return nil
}
