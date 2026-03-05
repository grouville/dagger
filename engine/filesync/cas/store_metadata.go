package cas

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"

	bkcache "github.com/dagger/dagger/internal/buildkit/cache"
	digest "github.com/opencontainers/go-digest"
)

const (
	keyScopeHeadScope      = "filesync.cas.scopeHead.scope"
	keyScopeHeadGeneration = "filesync.cas.scopeHead.generation"
	keyScopeHeadRootDigest = "filesync.cas.scopeHead.rootDigest"
	keyScopeHeadChainDepth = "filesync.cas.scopeHead.chainDepth"
	keyScopeHeadPayload    = "filesync.cas.scopeHead.payload"

	scopeHeadScopeIndex = keyScopeHeadScope + ":"

	keyManifestRootDigest = "filesync.cas.manifest.rootDigest"
	keyManifestPayload    = "filesync.cas.manifest.payload"

	manifestRootIndex = keyManifestRootDigest + ":"
)

type ScopeHeadStore struct {
	Store bkcache.MetadataStore
}

func (s ScopeHeadStore) Load(ctx context.Context, scope ScopeKey) (ScopeHead, bool, error) {
	mds, err := s.Store.Search(ctx, scopeHeadScopeIndex+scope.String(), false)
	if err != nil {
		return ScopeHead{}, false, fmt.Errorf("search scope head: %w", err)
	}

	var best ScopeHead
	var found bool
	for _, md := range mds {
		head, err := parseScopeHead(md)
		if err != nil {
			return ScopeHead{}, false, fmt.Errorf("parse scope head from %s: %w", md.ID(), err)
		}
		if head.Scope != scope {
			return ScopeHead{}, false, fmt.Errorf("scope mismatch in %s: got %q want %q", md.ID(), head.Scope, scope)
		}
		if !found || head.Generation > best.Generation {
			best = head
			found = true
		}
	}
	return best, found, nil
}

func (s ScopeHeadStore) Save(
	ctx context.Context,
	md bkcache.RefMetadata,
	head ScopeHead,
	expectedPrevGeneration uint64,
) error {
	if head.Scope == "" {
		return fmt.Errorf("scope head scope is empty")
	}
	if head.RootDigest == "" {
		return fmt.Errorf("scope head root digest is empty")
	}
	if err := head.RootDigest.Validate(); err != nil {
		return fmt.Errorf("invalid scope head root digest: %w", err)
	}

	current, found, err := s.Load(ctx, head.Scope)
	if err != nil {
		return err
	}
	if found {
		if current.Generation != expectedPrevGeneration {
			return fmt.Errorf("scope head generation mismatch: current=%d expected=%d", current.Generation, expectedPrevGeneration)
		}
		if head.Generation != current.Generation+1 {
			return fmt.Errorf("scope head generation must increment by 1: got=%d current=%d", head.Generation, current.Generation)
		}
	} else {
		if expectedPrevGeneration != 0 {
			return fmt.Errorf("scope head does not exist but expected previous generation=%d", expectedPrevGeneration)
		}
		if head.Generation != 1 {
			return fmt.Errorf("first scope head generation must be 1, got=%d", head.Generation)
		}
	}

	if head.MaterialRefID == "" {
		head.MaterialRefID = md.ID()
	}

	payload, err := marshalScopeHeadPayload(head)
	if err != nil {
		return err
	}

	if err := md.SetString(keyScopeHeadScope, head.Scope.String(), scopeHeadScopeIndex+head.Scope.String()); err != nil {
		return fmt.Errorf("set scope head scope: %w", err)
	}
	if err := md.SetString(keyScopeHeadGeneration, strconv.FormatUint(head.Generation, 10), ""); err != nil {
		return fmt.Errorf("set scope head generation: %w", err)
	}
	if err := md.SetString(keyScopeHeadRootDigest, head.RootDigest.String(), ""); err != nil {
		return fmt.Errorf("set scope head root digest: %w", err)
	}
	if err := md.SetString(keyScopeHeadChainDepth, strconv.FormatUint(uint64(head.ChainDepth), 10), ""); err != nil {
		return fmt.Errorf("set scope head chain depth: %w", err)
	}
	if err := md.SetExternal(keyScopeHeadPayload, payload); err != nil {
		return fmt.Errorf("set scope head payload: %w", err)
	}

	return nil
}

type ManifestStore struct {
	Store bkcache.MetadataStore
}

func (s ManifestStore) Save(md bkcache.RefMetadata, manifest Manifest) error {
	rootDigest := manifest.RootDigest
	var err error
	if rootDigest == "" {
		rootDigest, err = RootDigest(manifest)
		if err != nil {
			return err
		}
	}
	if err := rootDigest.Validate(); err != nil {
		return fmt.Errorf("invalid root digest: %w", err)
	}

	manifest.RootDigest = rootDigest
	payload, err := manifest.CanonicalBytes()
	if err != nil {
		return err
	}

	if err := md.SetString(keyManifestRootDigest, rootDigest.String(), manifestRootIndex+rootDigest.String()); err != nil {
		return fmt.Errorf("set manifest root digest: %w", err)
	}
	if err := md.SetExternal(keyManifestPayload, payload); err != nil {
		return fmt.Errorf("set manifest payload: %w", err)
	}
	return nil
}

func (s ManifestStore) Load(ctx context.Context, rootDigest digest.Digest) (Manifest, bool, error) {
	if rootDigest == "" {
		return Manifest{}, false, fmt.Errorf("root digest is empty")
	}
	if err := rootDigest.Validate(); err != nil {
		return Manifest{}, false, fmt.Errorf("invalid root digest: %w", err)
	}

	mds, err := s.Store.Search(ctx, manifestRootIndex+rootDigest.String(), false)
	if err != nil {
		return Manifest{}, false, fmt.Errorf("search manifest: %w", err)
	}
	if len(mds) == 0 {
		return Manifest{}, false, nil
	}

	var firstErr error
	for _, md := range mds {
		payload, err := md.GetExternal(keyManifestPayload)
		if err != nil {
			firstErr = fmt.Errorf("get manifest payload from %s: %w", md.ID(), err)
			continue
		}
		manifest, err := ParseManifest(payload)
		if err != nil {
			firstErr = fmt.Errorf("parse manifest from %s: %w", md.ID(), err)
			continue
		}
		if manifest.RootDigest == "" {
			computed, err := RootDigest(manifest)
			if err != nil {
				firstErr = fmt.Errorf("compute manifest root from %s: %w", md.ID(), err)
				continue
			}
			manifest.RootDigest = computed
		}
		if manifest.RootDigest != rootDigest {
			firstErr = fmt.Errorf("manifest root mismatch in %s: got %s want %s", md.ID(), manifest.RootDigest, rootDigest)
			continue
		}
		return manifest, true, nil
	}

	if firstErr != nil {
		return Manifest{}, false, firstErr
	}
	return Manifest{}, false, nil
}

type scopeHeadPayload struct {
	Scope         string `json:"scope"`
	RootDigest    string `json:"rootDigest"`
	MaterialRefID string `json:"materialRefId"`
	Generation    uint64 `json:"generation"`
	ChainDepth    uint32 `json:"chainDepth"`
}

func marshalScopeHeadPayload(head ScopeHead) ([]byte, error) {
	payload := scopeHeadPayload{
		Scope:         head.Scope.String(),
		RootDigest:    head.RootDigest.String(),
		MaterialRefID: head.MaterialRefID,
		Generation:    head.Generation,
		ChainDepth:    head.ChainDepth,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal scope head payload: %w", err)
	}
	return data, nil
}

func parseScopeHead(md bkcache.RefMetadata) (ScopeHead, error) {
	payloadBytes, err := md.GetExternal(keyScopeHeadPayload)
	if err != nil {
		return ScopeHead{}, fmt.Errorf("get scope head payload: %w", err)
	}
	if len(payloadBytes) == 0 {
		return ScopeHead{}, fmt.Errorf("scope head payload is empty")
	}

	var payload scopeHeadPayload
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return ScopeHead{}, fmt.Errorf("unmarshal scope head payload: %w", err)
	}

	head := ScopeHead{
		Scope:         ScopeKey(payload.Scope),
		RootDigest:    digest.Digest(payload.RootDigest),
		MaterialRefID: payload.MaterialRefID,
		Generation:    payload.Generation,
		ChainDepth:    payload.ChainDepth,
	}
	if head.Scope == "" {
		return ScopeHead{}, fmt.Errorf("scope head scope is empty")
	}
	if head.RootDigest == "" {
		return ScopeHead{}, fmt.Errorf("scope head root digest is empty")
	}
	if err := head.RootDigest.Validate(); err != nil {
		return ScopeHead{}, fmt.Errorf("invalid scope head root digest: %w", err)
	}
	if head.Generation == 0 {
		return ScopeHead{}, fmt.Errorf("scope head generation is zero")
	}
	if head.MaterialRefID == "" {
		head.MaterialRefID = md.ID()
	}

	return head, nil
}
