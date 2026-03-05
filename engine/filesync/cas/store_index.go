package cas

import (
	"context"
	"fmt"
	"sort"

	bkcache "github.com/dagger/dagger/internal/buildkit/cache"
	digest "github.com/opencontainers/go-digest"
)

const (
	keyRootIndexDigest = "filesync.cas.rootIndex.digest"
	rootIndexPrefix    = keyRootIndexDigest + ":"
)

type RootIndexStore struct {
	Store bkcache.MetadataStore
}

func (s RootIndexStore) Save(md bkcache.RefMetadata, rootDigest digest.Digest) error {
	if rootDigest == "" {
		return fmt.Errorf("root digest is empty")
	}
	if err := rootDigest.Validate(); err != nil {
		return fmt.Errorf("invalid root digest: %w", err)
	}
	return md.SetString(keyRootIndexDigest, rootDigest.String(), rootIndexPrefix+rootDigest.String())
}

func (s RootIndexStore) Resolve(ctx context.Context, rootDigest digest.Digest) ([]string, error) {
	if rootDigest == "" {
		return nil, fmt.Errorf("root digest is empty")
	}
	if err := rootDigest.Validate(); err != nil {
		return nil, fmt.Errorf("invalid root digest: %w", err)
	}

	mds, err := s.Store.Search(ctx, rootIndexPrefix+rootDigest.String(), false)
	if err != nil {
		return nil, fmt.Errorf("search root index: %w", err)
	}

	out := make([]string, 0, len(mds))
	seen := map[string]struct{}{}
	for _, md := range mds {
		id := md.ID()
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	sort.Strings(out)
	return out, nil
}
