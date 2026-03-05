package cas

import (
	"testing"

	"github.com/dagger/dagger/internal/buildkit/util/contentutil"
	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestBlobStoreRoundtrip(t *testing.T) {
	t.Parallel()

	store := BlobStore{Store: contentutil.NewBuffer()}
	payload := []byte("hello blob store")
	dgst := digest.FromBytes(payload)

	has, err := store.Has(t.Context(), dgst)
	assert.NilError(t, err)
	assert.Assert(t, !has)

	assert.NilError(t, store.PutBytes(t.Context(), dgst, payload))

	has, err = store.Has(t.Context(), dgst)
	assert.NilError(t, err)
	assert.Assert(t, has)

	readPayload, err := store.Open(t.Context(), dgst)
	assert.NilError(t, err)
	assert.DeepEqual(t, readPayload, payload)
}

func TestBlobStoreDigestMismatch(t *testing.T) {
	t.Parallel()

	store := BlobStore{Store: contentutil.NewBuffer()}
	payload := []byte("payload")
	wrongDigest := digest.FromString("different")

	err := store.PutBytes(t.Context(), wrongDigest, payload)
	assert.Assert(t, is.ErrorContains(err, "digest mismatch"))
}

func TestBlobStoreIdempotentWrites(t *testing.T) {
	t.Parallel()

	store := BlobStore{Store: contentutil.NewBuffer()}
	payload := []byte("repeat")
	dgst := digest.FromBytes(payload)

	assert.NilError(t, store.PutBytes(t.Context(), dgst, payload))
	assert.NilError(t, store.PutBytes(t.Context(), dgst, payload))

	readPayload, err := store.Open(t.Context(), dgst)
	assert.NilError(t, err)
	assert.DeepEqual(t, readPayload, payload)
}
