package cas

import (
	"bytes"
	"context"
	"fmt"
	"io"

	"github.com/containerd/containerd/v2/core/content"
	cerrdefs "github.com/containerd/errdefs"
	digest "github.com/opencontainers/go-digest"
	ocispecs "github.com/opencontainers/image-spec/specs-go/v1"
)

type BlobStore struct {
	Store blobContentStore
}

type blobContentStore interface {
	Info(context.Context, digest.Digest) (content.Info, error)
	Writer(context.Context, ...content.WriterOpt) (content.Writer, error)
	ReaderAt(context.Context, ocispecs.Descriptor) (content.ReaderAt, error)
}

func (s BlobStore) Has(ctx context.Context, dgst digest.Digest) (bool, error) {
	if dgst == "" {
		return false, fmt.Errorf("blob digest is empty")
	}
	if err := dgst.Validate(); err != nil {
		return false, fmt.Errorf("invalid blob digest: %w", err)
	}

	_, err := s.Store.Info(ctx, dgst)
	if err == nil {
		return true, nil
	}
	if cerrdefs.IsNotFound(err) {
		return false, nil
	}
	return false, fmt.Errorf("blob info: %w", err)
}

func (s BlobStore) PutBytes(ctx context.Context, dgst digest.Digest, payload []byte) error {
	if dgst == "" {
		return fmt.Errorf("blob digest is empty")
	}
	if err := dgst.Validate(); err != nil {
		return fmt.Errorf("invalid blob digest: %w", err)
	}
	if actual := digest.FromBytes(payload); actual != dgst {
		return fmt.Errorf("blob digest mismatch: got=%s expected=%s", actual, dgst)
	}

	exists, err := s.Has(ctx, dgst)
	if err != nil {
		return err
	}
	if exists {
		return nil
	}

	desc := ocispecs.Descriptor{
		Digest: dgst,
		Size:   int64(len(payload)),
	}
	ref := "filesync-cas-blob-" + dgst.Encoded()
	writer, err := content.OpenWriter(ctx, s.Store, content.WithRef(ref), content.WithDescriptor(desc))
	if err != nil {
		return fmt.Errorf("open writer: %w", err)
	}
	defer writer.Close()

	if _, err := io.Copy(writer, bytes.NewReader(payload)); err != nil {
		return fmt.Errorf("copy payload: %w", err)
	}
	if err := writer.Commit(ctx, int64(len(payload)), dgst); err != nil {
		if cerrdefs.IsAlreadyExists(err) || cerrdefs.IsConflict(err) {
			return nil
		}
		return fmt.Errorf("commit blob: %w", err)
	}

	return nil
}

func (s BlobStore) Open(ctx context.Context, dgst digest.Digest) ([]byte, error) {
	if dgst == "" {
		return nil, fmt.Errorf("blob digest is empty")
	}
	if err := dgst.Validate(); err != nil {
		return nil, fmt.Errorf("invalid blob digest: %w", err)
	}

	info, err := s.Store.Info(ctx, dgst)
	if err != nil {
		return nil, fmt.Errorf("blob info: %w", err)
	}
	desc := ocispecs.Descriptor{
		Digest: dgst,
		Size:   info.Size,
	}
	data, err := content.ReadBlob(ctx, s.Store, desc)
	if err != nil {
		return nil, fmt.Errorf("read blob: %w", err)
	}
	return data, nil
}
