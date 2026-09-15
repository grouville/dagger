package core

import (
	"testing"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
)

type stubSnapshotRef struct{ bkcache.ImmutableRef }

func TestHTTPStateRevalidationNeeded(t *testing.T) {
	content := digest.FromString("pinned")
	other := digest.FromString("other")

	cached := &HTTPState{URL: "https://example.com/pkg.deb", ContentDigest: content, snapshot: stubSnapshotRef{}}
	require.False(t, cached.revalidationNeeded(content), "cached content with the requested checksum needs no request")
	require.True(t, cached.revalidationNeeded(other), "a different checksum must be fetched and verified")
	require.True(t, cached.revalidationNeeded(""), "without a checksum the per-session revalidation stays")

	empty := &HTTPState{URL: "https://example.com/pkg.deb"}
	require.True(t, empty.revalidationNeeded(content), "nothing cached yet")

	digestOnly := &HTTPState{URL: "https://example.com/pkg.deb", ContentDigest: content}
	require.True(t, digestOnly.revalidationNeeded(content), "a digest without its snapshot cannot be served")
}
