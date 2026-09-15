package filetree

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"math"
	"strconv"
	"time"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/errdefs"
	"github.com/dagger/dagger/internal/buildkit/identity"
	"github.com/opencontainers/go-digest"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
)

const (
	// Bound individual directory nodes, not file contents or the complete tree.
	maxTreeSize      = 64 << 20
	treeLabel        = "dagger.io/filetree.version"
	childLabelPrefix = "containerd.io/gc.ref.content.dagger.filetree."
)

// Store uses the engine's existing namespaced, metadata-backed content store.
// It does not own a separate blob directory, snapshot, or garbage collector.
type Store struct {
	blobs content.Store
}

func NewStore(blobs content.Store) *Store {
	return &Store{blobs: blobs}
}

// Ingest borrows an operation lease. The caller must keep that lease alive until
// result ownership has been attached, including on an already-present root.
// It must not release the lease while writes are in flight.
type Ingest struct {
	store  *Store
	ctx    context.Context
	leases leases.Manager
	lease  leases.Lease
}

// Ingest requires a non-flat lease: retaining a tree must also retain its
// descendants. In particular, existing flat snapshot-owner leases cannot be
// used here. Lease creation and the handoff to result ownership belong to the
// caller, not this storage primitive.
func (s *Store) Ingest(ctx context.Context, lm leases.Manager) (*Ingest, error) {
	id, ok := leases.FromContext(ctx)
	if !ok || id == "" {
		return nil, errors.New("filetree ingest requires an operation lease")
	}
	if lm == nil {
		return nil, errors.New("filetree ingest requires a lease manager")
	}
	found, err := lm.List(ctx, "id=="+strconv.Quote(id))
	if err != nil {
		return nil, fmt.Errorf("inspect filetree operation lease: %w", err)
	}
	for _, lease := range found {
		if lease.ID != id {
			continue
		}
		if _, flat := lease.Labels["containerd.io/gc.flat"]; flat {
			return nil, errors.New("filetree ingest requires a non-flat operation lease")
		}
		return &Ingest{store: s, ctx: ctx, leases: lm, lease: lease}, nil
	}
	return nil, fmt.Errorf("filetree operation lease %q is missing", id)
}

// Retain pins an existing object before checking it. Merely calling Info is
// insufficient: GC could remove that object between lookup and publication.
func (in *Ingest) Retain(obj Object) error {
	if err := obj.Validate(); err != nil {
		return err
	}
	if err := in.leases.AddResource(in.ctx, in.lease, leases.Resource{
		Type: "content", ID: obj.Digest.String(),
	}); err != nil {
		return fmt.Errorf("retain filetree object %s: %w", obj.Digest, err)
	}
	info, err := in.store.blobs.Info(in.ctx, obj.Digest)
	if err != nil {
		return fmt.Errorf("inspect filetree object %s: %w", obj.Digest, err)
	}
	if info.Size != obj.Size {
		return fmt.Errorf("filetree object %s: size %d, expected %d", obj.Digest, info.Size, obj.Size)
	}
	return nil
}

// PutFile streams bytes into the existing content store. It checks the exact
// length (including empty files); containerd hashes and commits the bytes.
// No second payload hasher, full-file buffer or mutable-source hardlink is used.
func (in *Ingest) PutFile(r io.Reader, size int64) (Object, error) {
	return in.put(r, size, "", nil)
}

// PutTree checks and retains children before committing the node and its GC
// links. Hardlink targets are root-relative, so resolving them is the complete
// tree validator's responsibility, not an individual node's.
func (in *Ingest) PutTree(tree Tree) (Object, error) {
	if err := checkTreeBudget(tree, maxTreeSize); err != nil {
		return Object{}, err
	}
	data, err := Encode(tree)
	if err != nil {
		return Object{}, err
	}
	if len(data) > maxTreeSize {
		return Object{}, errors.New("filetree node exceeds size limit")
	}
	for _, child := range tree.References() {
		if err := in.Retain(child); err != nil {
			return Object{}, err
		}
	}
	for _, entry := range tree.Entries {
		if entry.Kind == Directory {
			if _, err := in.store.ReadTree(in.ctx, *entry.Object); err != nil {
				return Object{}, fmt.Errorf("directory %q: %w", entry.Name, err)
			}
		}
	}
	labels := treeLabels(tree)
	obj, err := in.put(bytes.NewReader(data), int64(len(data)), digest.FromBytes(data), labels)
	if err != nil {
		return Object{}, err
	}
	// containerd's already-present fast path does not apply commit options.
	// Repair only our deterministic fields; preserve unrelated content labels.
	info, err := in.store.blobs.Info(in.ctx, obj.Digest)
	if err != nil {
		return Object{}, err
	}
	var fields []string
	for key, value := range labels {
		if info.Labels[key] != value {
			fields = append(fields, "labels."+key)
		}
	}
	if len(fields) > 0 {
		_, err = in.store.blobs.Update(in.ctx, content.Info{Digest: obj.Digest, Labels: labels}, fields...)
		if err != nil {
			return Object{}, fmt.Errorf("link filetree children: %w", err)
		}
	}
	return obj, nil
}

func (in *Ingest) put(r io.Reader, size int64, expected digest.Digest, labels map[string]string) (_ Object, rerr error) {
	if size < 0 || size == math.MaxInt64 {
		return Object{}, fmt.Errorf("invalid filetree object size %d", size)
	}
	ref := "filetree-" + identity.NewID()
	w, err := in.store.blobs.Writer(in.ctx, content.WithRef(ref), content.WithDescriptor(ocispec.Descriptor{
		Digest: expected, Size: size,
	}))
	if err != nil {
		if expected != "" && errdefs.IsAlreadyExists(err) {
			obj := Object{Digest: expected, Size: size}
			return obj, in.Retain(obj)
		}
		return Object{}, fmt.Errorf("open filetree writer: %w", err)
	}
	defer func() {
		rerr = errors.Join(rerr, w.Close())
		if rerr != nil {
			// Close alone leaves a resumable ingest. Our unique ref is never
			// resumed, so abort it even when the request was canceled.
			ctx, cancel := context.WithTimeout(context.WithoutCancel(in.ctx), 30*time.Second)
			defer cancel()
			if err := in.store.blobs.Abort(ctx, ref); err != nil && !errdefs.IsNotFound(err) {
				rerr = errors.Join(rerr, fmt.Errorf("abort filetree ingest: %w", err))
			}
		}
	}()

	status, err := w.Status()
	if err != nil {
		return Object{}, fmt.Errorf("inspect filetree writer: %w", err)
	}
	if status.Offset < 0 || status.Offset > size {
		return Object{}, fmt.Errorf("filetree writer offset %d exceeds size %d", status.Offset, size)
	}
	copied, err := content.CopyReader(w, io.LimitReader(&contextReader{ctx: in.ctx, r: r}, size+1))
	if err != nil {
		return Object{}, fmt.Errorf("write filetree object: %w", err)
	}
	// A shared blob from another namespace can start at the full offset.
	// CopyReader consumes the prefix but counts only newly written bytes.
	n := status.Offset + copied
	if n != size {
		return Object{}, fmt.Errorf("filetree object length %d, expected %d", n, size)
	}
	if err := w.Commit(in.ctx, size, expected, content.WithLabels(labels)); err != nil && !errdefs.IsAlreadyExists(err) {
		return Object{}, fmt.Errorf("commit filetree object: %w", err)
	}
	// Writer.Digest is guaranteed only after commit. Reuse containerd's digest
	// instead of hashing file payloads a second time in this package.
	obj := Object{Digest: w.Digest(), Size: size}
	return obj, in.Retain(obj)
}

// OpenFile returns committed bytes. The caller must retain the object for the
// lifetime of the reader and close the reader when finished.
func (s *Store) OpenFile(ctx context.Context, obj Object) (content.ReaderAt, error) {
	if err := obj.Validate(); err != nil {
		return nil, err
	}
	r, err := s.blobs.ReaderAt(ctx, ocispec.Descriptor{Digest: obj.Digest, Size: obj.Size})
	if err != nil {
		return nil, err
	}
	if r.Size() != obj.Size {
		return nil, errors.Join(fmt.Errorf("filetree object %s has unexpected size %d", obj.Digest, r.Size()), r.Close())
	}
	return r, nil
}

// ReadTree verifies the canonical node bytes and its outgoing GC links. Raw
// file contents which happen to encode a tree are not yet a published node.
func (s *Store) ReadTree(ctx context.Context, obj Object) (Tree, error) {
	if obj.Size > maxTreeSize {
		return Tree{}, errors.New("filetree node exceeds size limit")
	}
	r, err := s.OpenFile(ctx, obj)
	if err != nil {
		return Tree{}, err
	}
	data, readErr := io.ReadAll(content.NewReader(r))
	if err := errors.Join(readErr, r.Close()); err != nil {
		return Tree{}, err
	}
	if digest.FromBytes(data) != obj.Digest {
		return Tree{}, errors.New("filetree node digest mismatch")
	}
	tree, err := Decode(data)
	if err != nil {
		return Tree{}, err
	}
	info, err := s.blobs.Info(ctx, obj.Digest)
	if err != nil {
		return Tree{}, err
	}
	for key, value := range treeLabels(tree) {
		if info.Labels[key] != value {
			return Tree{}, fmt.Errorf("filetree node %s has incomplete GC links", obj.Digest)
		}
	}
	return tree, nil
}

func treeLabels(tree Tree) map[string]string {
	labels := map[string]string{treeLabel: strconv.Itoa(TreeVersion)}
	for i, child := range tree.References() {
		labels[childLabelPrefix+strconv.Itoa(i)] = child.Digest.String()
	}
	return labels
}

// Reject obviously oversized inputs before Encode clones byte strings and
// allocates JSON. The fixed costs are lower bounds on valid JSON structures;
// the exact encoded-size check still applies afterwards. Subtract each length
// separately so a hostile aggregate cannot overflow the budget calculation.
func checkTreeBudget(tree Tree, limit int) error {
	remaining := limit
	take := func(sizes ...int) bool {
		for _, size := range sizes {
			if size > remaining {
				return false
			}
			remaining -= size
		}
		return true
	}
	metadata := func(m Metadata) bool {
		if !take(32) {
			return false
		}
		for _, xattr := range m.Xattrs {
			if !take(24, len(xattr.Name), len(xattr.Value)) {
				return false
			}
		}
		return true
	}
	tooLarge := errors.New("filetree node exceeds size limit")
	if !take(16) || !metadata(tree.Metadata) {
		return tooLarge
	}
	for _, entry := range tree.Entries {
		if !take(32, len(entry.Name), len(entry.Linkname)) {
			return tooLarge
		}
		if entry.Metadata != nil && !metadata(*entry.Metadata) {
			return tooLarge
		}
		if entry.Object != nil && !take(16, len(entry.Object.Digest)) {
			return tooLarge
		}
	}
	return nil
}

type contextReader struct {
	ctx context.Context
	r   io.Reader
}

func (r *contextReader) Read(p []byte) (int, error) {
	if err := context.Cause(r.ctx); err != nil {
		return 0, err
	}
	return r.r.Read(p)
}
