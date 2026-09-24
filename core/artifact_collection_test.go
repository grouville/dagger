package core

import (
	"context"
	"errors"
	"fmt"
	"math/rand/v2"
	"slices"
	"sync/atomic"
	"testing"
	"time"

	"github.com/dagger/dagger/core/dagaddress"
	"github.com/dagger/dagger/dagql"
	"github.com/stretchr/testify/require"
)

func TestArtifactCollectionSharedDiscovery(t *testing.T) {
	all, keys, calls := artifactDiscoveryFixture(100, 16, 8)
	selected := all.filter(func(*Artifact) bool { return true }).filter(func(*Artifact) bool { return true })
	require.NotSame(t, all.Entries[0].Node.Parent, selected.Entries[0].Node.Parent)
	for i := range 2 {
		expanded, err := selected.expand(t.Context(), keys)
		require.NoError(t, err)
		require.Len(t, expanded.Entries, 100*16*8)
		require.EqualValues(t, (i+1)*17, calls.Load(), "one enumeration per receiver, with no reuse across requests")
		for _, source := range []*Artifacts{all, selected} {
			for _, entry := range source.Entries {
				for node := entry.Node; node != nil; node = node.Parent {
					require.Nil(t, node.CollectionKey)
				}
			}
		}
	}
}

func TestArtifactCollectionSharedDiscoveryWorkspaceScope(t *testing.T) {
	all, _, _ := artifactDiscoveryFixture(1, 1, 1)
	for _, name := range []string{"first", "second"} {
		ws, err := dagql.NewResultForCall(&Workspace{Address: name}, &dagql.ResultCall{})
		require.NoError(t, err)
		entry := *all.Entries[0]
		entry.Workspace = dagql.ObjectResult[*Workspace]{Result: ws}
		all.Entries = append(all.Entries, &entry)
	}
	all.Entries = all.Entries[1:]
	var calls atomic.Int32
	expanded, err := all.expand(t.Context(), func(_ context.Context, receiver *Artifact) ([]collectionKey, error) {
		calls.Add(1)
		return []collectionKey{{text: receiver.Workspace.Self().Address}}, nil
	})
	require.NoError(t, err)
	require.EqualValues(t, 4, calls.Load())
	require.Len(t, expanded.Entries, 2)
	for i, name := range []string{"first", "second"} {
		require.Equal(t, []*ArtifactDimensionKey{{Dimension: "App.modules", Key: name}, {Dimension: "Module.tests", Key: name}}, expanded.Entries[i].DimensionKeys)
	}
}

func TestArtifactCollectionSharedDiscoveryDoesNotRetainKeysOrErrors(t *testing.T) {
	all, _, _ := artifactDiscoveryFixture(2, 1, 1)
	unavailable := errors.New("temporarily unavailable")
	for _, value := range []string{"before", "error", "after"} {
		expanded, err := all.expand(t.Context(), func(context.Context, *Artifact) ([]collectionKey, error) {
			if value == "error" {
				return nil, unavailable
			}
			return []collectionKey{{text: value}}, nil
		})
		if value == "error" {
			require.ErrorIs(t, err, unavailable)
			continue
		}
		require.NoError(t, err)
		require.Len(t, expanded.Entries, 2)
		for _, entry := range expanded.Entries {
			require.Equal(t, []*ArtifactDimensionKey{
				{Dimension: "App.modules", Key: value},
				{Dimension: "Module.tests", Key: value},
			}, entry.DimensionKeys)
		}
	}
}

func TestArtifactCollectionSharedDiscoveryFailure(t *testing.T) {
	all, _, _ := artifactDiscoveryFixture(100, 16, 8)
	failure := errors.New("keys unavailable")
	ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
	defer cancel()
	var calls atomic.Int32
	expanded, err := all.expand(ctx, func(context.Context, *Artifact) ([]collectionKey, error) {
		calls.Add(1)
		return nil, failure
	})
	require.ErrorIs(t, err, failure)
	require.Nil(t, expanded)
	require.EqualValues(t, 1, calls.Load())
}

func TestArtifactCollectionDimensionKeyPruning(t *testing.T) {
	// Compare the index to the exhaustive definition on overlapping, unsorted
	// paths with different dimension chains, including collection/item pairs
	// at the same address. No values are evaluated by either implementation.
	rng := rand.New(rand.NewPCG(1, 2))
	all := &Artifacts{}
	for range 300 {
		entry := &Artifact{}
		for range rng.IntN(4) {
			entry.Path = append(entry.Path, fmt.Sprint(rng.IntN(3)))
		}
		for range rng.IntN(4) {
			dim := &ArtifactDimension{Identifier: fmt.Sprint(rng.IntN(3))}
			entry.Node = &ModTreeNode{Parent: entry.Node, CollectionDimension: dim}
		}
		all.Entries = append(all.Entries, entry)
	}
	for _, selector := range []ArtifactSelector{
		{},
		{Dimensions: []ArtifactDimensionFilter{{Dimension: "1"}}},
		{Dimensions: []ArtifactDimensionFilter{{Dimension: "1", Keys: []string{}}}},
		{DimensionAlternatives: [][]string{{"1", "2"}}},
		{ExcludedURIs: []string{"dag://0?1=x"}},
	} {
		all.Selector = selector
		for _, dimension := range []string{"0", "1", "2", "missing"} {
			var want []*Artifact
			for _, candidate := range all.Entries {
				childDims := candidate.DimensionDefinitions()
				covered := false
				if len(selector.ExcludedURIs) == 0 {
					for _, ancestor := range all.Entries {
						parentDims := ancestor.DimensionDefinitions()
						if len(ancestor.Path) > len(candidate.Path) || len(parentDims) > len(childDims) ||
							len(ancestor.Path) == len(candidate.Path) && len(parentDims) == len(childDims) {
							continue
						}
						if slices.Equal(ancestor.Path, candidate.Path[:len(ancestor.Path)]) && all.matchesDimensionFilters(parentDims) &&
							slices.ContainsFunc(parentDims, func(d *ArtifactDimension) bool { return d.Identifier == dimension }) &&
							slices.EqualFunc(parentDims, childDims[:len(parentDims)], func(a, b *ArtifactDimension) bool { return a.Identifier == b.Identifier }) {
							covered = true
							break
						}
					}
				}
				if !covered {
					want = append(want, candidate)
				}
			}
			require.Equal(t, want, all.ForDimensionKeys(dimension).Entries)
		}
	}
}

func collectionArtifactFixture() *Artifacts {
	artifacts := &Artifacts{}
	for _, field := range []string{"items", "other"} {
		dim := &ArtifactDimension{Identifier: "App." + field, Name: "item", QualifiedName: "app-" + field}
		collection := &ModTreeNode{Name: field}
		artifacts.Entries = append(artifacts.Entries, &Artifact{Path: []string{field}, Node: collection, TypeName: "Items"})
		for _, key := range []string{"b", "a"} {
			artifacts.Entries = append(artifacts.Entries, &Artifact{
				Path: []string{field}, TypeName: "Item",
				Node: &ModTreeNode{Parent: collection, Name: "get", CollectionDimension: dim, CollectionKey: &key},
			})
		}
	}
	return artifacts
}

// parallelCollectionFixture exercises both independent templates and multiple
// receivers produced by a single template's outer collection.
func parallelCollectionFixture(nested bool) (*Artifacts, artifactCollectionKeyFunc) {
	all := &Artifacts{}
	outer := &ArtifactDimension{Identifier: "App.modules", Name: "module"}
	inner := &ArtifactDimension{Identifier: "Module.tests", Name: "test"}
	if nested {
		root := &ModTreeNode{Name: "modules"}
		module := &ModTreeNode{Name: "get", Parent: root, CollectionDimension: outer}
		tests := &ModTreeNode{Name: "tests", Parent: module}
		item := &ModTreeNode{Name: "get", Parent: tests, CollectionDimension: inner}
		all.Entries = append(all.Entries, &Artifact{Path: []string{"modules", "tests", "check"}, Node: &ModTreeNode{Name: "check", Parent: item}})
	} else {
		for _, name := range []string{"b", "a"} {
			root := &ModTreeNode{Name: name}
			item := &ModTreeNode{Name: "get", Parent: root, CollectionDimension: inner}
			all.Entries = append(all.Entries, &Artifact{Path: []string{name, "check"}, Node: &ModTreeNode{Name: "check", Parent: item}})
		}
	}
	return all, func(_ context.Context, receiver *Artifact) ([]collectionKey, error) {
		if nested && receiver.Node.Name == "modules" {
			return []collectionKey{{text: "b"}, {text: "a"}}, nil
		}
		return nil, fmt.Errorf("unexpected collection receiver %q (leaf must remain deferred)", receiver.Node.Name)
	}
}

func parallelCollectionReceiver(nested bool, receiver *Artifact) string {
	if nested && receiver.Node.Name == "tests" {
		return *receiver.Node.Parent.CollectionKey
	}
	return receiver.Node.Name
}

func TestArtifactCollectionParallelExpansion(t *testing.T) {
	for _, nested := range []bool{false, true} {
		t.Run(fmt.Sprintf("nested=%t", nested), func(t *testing.T) {
			all, fallback := parallelCollectionFixture(nested)
			// The deadline only guards against deadlocks in a serial regression;
			// overlap is proved by both receivers reaching the barrier.
			ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
			defer cancel()
			var arrived atomic.Int32
			ready := make(chan struct{})
			secondReturned := make(chan struct{})
			keys := func(ctx context.Context, receiver *Artifact) ([]collectionKey, error) {
				name := parallelCollectionReceiver(nested, receiver)
				if name != "b" && name != "a" {
					return fallback(ctx, receiver)
				}
				if arrived.Add(1) == 2 {
					close(ready)
				}
				select {
				case <-ready:
				case <-ctx.Done():
					return nil, ctx.Err()
				}
				if name == "b" {
					select {
					case <-secondReturned:
					case <-ctx.Done():
						return nil, ctx.Err()
					}
				} else {
					close(secondReturned)
				}
				return []collectionKey{{text: "z"}, {text: "x"}}, nil
			}
			expanded, err := all.expand(ctx, keys)
			require.NoError(t, err)
			require.EqualValues(t, 2, arrived.Load())
			var uris []string
			for _, item := range expanded.Entries {
				uri, err := item.URI(ArtifactURIOpts{DimensionKeys: true})
				require.NoError(t, err)
				uris = append(uris, uri)
			}
			if nested {
				require.Equal(t, []string{
					"dag://modules/tests/check?module=b&test=z", "dag://modules/tests/check?module=b&test=x",
					"dag://modules/tests/check?module=a&test=z", "dag://modules/tests/check?module=a&test=x",
				}, uris)
			} else {
				require.Equal(t, []string{
					"dag://b/check?test=z", "dag://b/check?test=x", "dag://a/check?test=z", "dag://a/check?test=x",
				}, uris)
			}
			for _, template := range all.Entries {
				require.Nil(t, template.Node.Parent.CollectionKey, "templates must not be mutated")
			}
		})
	}
}

func TestArtifactCollectionParallelCancellation(t *testing.T) {
	for _, nested := range []bool{false, true} {
		for _, external := range []bool{false, true} {
			t.Run(fmt.Sprintf("nested=%t/external=%t", nested, external), func(t *testing.T) {
				all, fallback := parallelCollectionFixture(nested)
				ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
				defer cancel()
				siblingStarted := make(chan struct{})
				siblingStopped := make(chan struct{})
				failure := errors.New("enumeration failed")
				keys := func(ctx context.Context, receiver *Artifact) ([]collectionKey, error) {
					switch parallelCollectionReceiver(nested, receiver) {
					case "b":
						select {
						case <-siblingStarted:
						case <-ctx.Done():
							return nil, ctx.Err()
						}
						if external {
							cancel()
							return nil, ctx.Err()
						}
						return nil, failure
					case "a":
						close(siblingStarted)
						<-ctx.Done()
						close(siblingStopped)
						return nil, ctx.Err()
					default:
						return fallback(ctx, receiver)
					}
				}
				expanded, err := all.expand(ctx, keys)
				if external {
					require.ErrorIs(t, err, context.Canceled)
				} else {
					require.ErrorIs(t, err, failure)
				}
				require.Nil(t, expanded, "do not expose partial expansion")
				select {
				case <-siblingStopped:
				default:
					t.Fatal("expansion must wait for canceled workers")
				}
			})
		}
	}
}

func TestArtifactCollectionExpansionPrunesParents(t *testing.T) {
	all, fallback := parallelCollectionFixture(true)
	for i, selected := range []*Artifacts{
		all.FilterDimensionKeys("module", []string{"a"}).FilterDimensionKeys("test", []string{"x"}),
		all.FilterDimensionKeys("module", []string{}),
	} {
		var calls atomic.Int32
		expanded, err := selected.expand(t.Context(), func(ctx context.Context, receiver *Artifact) ([]collectionKey, error) {
			if receiver.Node.Name == "tests" {
				if *receiver.Node.Parent.CollectionKey != "a" {
					return nil, errors.New("filtered parent was evaluated")
				}
				calls.Add(1)
				return []collectionKey{{text: "z"}, {text: "x"}}, nil
			}
			return fallback(ctx, receiver)
		})
		require.NoError(t, err)
		require.EqualValues(t, 1-i, calls.Load())
		require.Len(t, expanded.Entries, int(calls.Load()))
		if calls.Load() != 0 {
			require.Equal(t, []*ArtifactDimensionKey{{Dimension: "App.modules", Key: "a"}, {Dimension: "Module.tests", Key: "x"}}, expanded.Entries[0].DimensionKeys)
		}
	}
}

func TestArtifactCollectionDimensionBinding(t *testing.T) {
	all := collectionArtifactFixture()
	_, err := all.FilterDimensionKeys("item", []string{"a"}).BindDimensions()
	require.ErrorContains(t, err, "ambiguous dimension")
	for _, selected := range []*Artifacts{
		all.FilterDimensionKeys("item", []string{"a"}).FilterPath([]string{"items"}),
		all.FilterPath([]string{"items"}).FilterDimensionKeys("item", []string{"a"}),
		all.FilterPath([]string{"items"}).FilterDimensionKeys("app-items", []string{"a"}),
		all.FilterPath([]string{"items"}).FilterDimensionKeys("App.items", []string{"a"}),
	} {
		expanded, err := selected.Expand(context.Background())
		require.NoError(t, err)
		require.Len(t, expanded.Entries, 1)
		require.Equal(t, []*ArtifactDimensionKey{{Dimension: "App.items", Key: "a"}}, expanded.Entries[0].DimensionKeys)
		uri, err := expanded.Entries[0].URI(ArtifactURIOpts{DimensionKeys: true})
		require.NoError(t, err)
		require.Equal(t, "dag://items?item=a", uri)
		addr, err := dagaddress.Parse(expanded.URI())
		require.NoError(t, err)
		roundTrip, err := all.FilterURI(addr)
		require.NoError(t, err)
		roundTrip, err = roundTrip.Expand(context.Background())
		require.NoError(t, err)
		require.Len(t, roundTrip.Entries, 1)
		require.Equal(t, expanded.Entries[0].DimensionKeys, roundTrip.Entries[0].DimensionKeys)
	}
	require.Empty(t, all.Selector.Dimensions)
}

func TestArtifactCollectionDimensionAlternatives(t *testing.T) {
	all := collectionArtifactFixture()
	selected := all.FilterDimensions([]string{"app-items", "app-other"})
	expanded, err := selected.Expand(context.Background())
	require.NoError(t, err)
	require.Len(t, expanded.Entries, 4)
	narrowed, err := selected.FilterPath([]string{"items"}).FilterDimensionKeys("item", []string{"a"}).Expand(context.Background())
	require.NoError(t, err)
	require.Len(t, narrowed.Entries, 1)
	for _, names := range [][]string{nil, {}, {"missing"}} {
		empty, err := all.FilterDimensions(names).Expand(context.Background())
		require.NoError(t, err)
		require.Empty(t, empty.Entries)
	}
}

func TestArtifactCollectionExactEndpoints(t *testing.T) {
	all := collectionArtifactFixture()
	collection, err := all.FilterPath([]string{"items"}).Expand(context.Background())
	require.NoError(t, err)
	require.Len(t, collection.Entries, 1)
	require.Equal(t, "Items", collection.Entries[0].TypeName)
	wildcard, err := all.FilterPattern("item*")
	require.NoError(t, err)
	wildcard, err = wildcard.FilterPattern("*s")
	require.NoError(t, err)
	items, err := wildcard.Expand(context.Background())
	require.NoError(t, err)
	require.Len(t, items.Entries, 3)
	addr, err := dagaddress.Parse(wildcard.URI())
	require.NoError(t, err)
	roundTrip, err := all.FilterURI(addr)
	require.NoError(t, err)
	roundTrip, err = roundTrip.Expand(context.Background())
	require.NoError(t, err)
	require.Len(t, roundTrip.Entries, 3)
}

func TestArtifactCollectionExclusions(t *testing.T) {
	all, err := collectionArtifactFixture().FilterPattern("items*")
	require.NoError(t, err)
	exclusion, err := dagaddress.Parse("items?item=a")
	require.NoError(t, err)
	selected, err := all.WithoutURI(exclusion)
	require.NoError(t, err)
	require.Empty(t, all.Selector.ExcludedURIs)
	expanded, err := selected.Expand(t.Context())
	require.NoError(t, err)
	require.Len(t, expanded.Entries, 2)
	require.Empty(t, expanded.Entries[0].DimensionKeys)
	require.Equal(t, []*ArtifactDimensionKey{{Dimension: "App.items", Key: "b"}}, expanded.Entries[1].DimensionKeys)
	for _, key := range []string{"a", "b"} {
		narrowed := all.FilterDimensionKeys("item", []string{key})
		narrowed, err = narrowed.WithoutURI(exclusion)
		require.NoError(t, err)
		expanded, err := narrowed.Expand(t.Context())
		require.NoError(t, err)
		if key == "a" {
			require.Empty(t, expanded.Entries)
		} else {
			require.Len(t, expanded.Entries, 1)
			require.Equal(t, []*ArtifactDimensionKey{{Dimension: "App.items", Key: "b"}}, expanded.Entries[0].DimensionKeys)
		}
	}
}
