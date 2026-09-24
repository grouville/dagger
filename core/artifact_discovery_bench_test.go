package core

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"
)

// Model many operations sharing nested collections. Keys are already in memory
// so this measures discovery overhead independently of module/container startup.
func artifactDiscoveryFixture(paths, modules, tests int) (*Artifacts, artifactCollectionKeyFunc, *atomic.Int64) {
	outer := &ArtifactDimension{Identifier: "App.modules", Name: "module"}
	inner := &ArtifactDimension{Identifier: "Module.tests", Name: "test"}
	root := &ModTreeNode{Name: "modules"}
	module := &ModTreeNode{Name: "get", Parent: root, CollectionDimension: outer}
	receiver := &ModTreeNode{Name: "tests", Parent: module}
	item := &ModTreeNode{Name: "get", Parent: receiver, CollectionDimension: inner}
	all := &Artifacts{}
	for i := range paths {
		name := fmt.Sprintf("check%d", i)
		all.Entries = append(all.Entries, &Artifact{Path: []string{"modules", "tests", name}, Node: &ModTreeNode{Name: name, Parent: item}})
	}
	keys := func(n int) []collectionKey {
		result := make([]collectionKey, n)
		for i := range result {
			result[i].text = fmt.Sprint(i)
		}
		return result
	}
	moduleKeys, testKeys := keys(modules), keys(tests)
	calls := new(atomic.Int64)
	return all, func(_ context.Context, artifact *Artifact) ([]collectionKey, error) {
		calls.Add(1)
		switch artifact.Node.Name {
		case "modules":
			return moduleKeys, nil
		case "tests":
			return testKeys, nil
		default:
			return nil, fmt.Errorf("evaluated leaf %q", artifact.Node.Name)
		}
	}, calls
}

func BenchmarkArtifactDiscoveryExpand(b *testing.B) {
	for _, size := range []struct{ paths, modules, tests int }{{100, 1, 1}, {1000, 1, 1}, {100, 16, 8}} {
		b.Run(fmt.Sprintf("paths=%d/modules=%d/tests=%d", size.paths, size.modules, size.tests), func(b *testing.B) {
			all, keys, calls := artifactDiscoveryFixture(size.paths, size.modules, size.tests)
			b.ReportAllocs()
			for b.Loop() {
				result, err := all.expand(b.Context(), keys)
				if err != nil {
					b.Fatal(err)
				}
				if len(result.Entries) != size.paths*size.modules*size.tests {
					b.Fatalf("unexpected item count: %d", len(result.Entries))
				}
			}
			b.ReportMetric(float64(calls.Load())/float64(b.N), "receivers/op")
		})
	}
}

func BenchmarkArtifactDiscoveryDimensionKeys(b *testing.B) {
	for _, paths := range []int{100, 1000} {
		b.Run(fmt.Sprintf("paths=%d", paths), func(b *testing.B) {
			all := &Artifacts{}
			for i := range paths {
				name := fmt.Sprintf("collection%d", i)
				dim := &ArtifactDimension{Identifier: "App.items", Name: "item"}
				item := &ModTreeNode{Name: "get", Parent: &ModTreeNode{Name: name}, CollectionDimension: dim}
				all.Entries = append(all.Entries, &Artifact{Path: []string{name}, Node: item})
				for j := range 4 {
					leaf := fmt.Sprintf("leaf%d", j)
					all.Entries = append(all.Entries, &Artifact{Path: []string{name, leaf}, Node: &ModTreeNode{Name: leaf, Parent: item}})
				}
			}
			b.ReportAllocs()
			for b.Loop() {
				result := all.ForDimensionKeys("App.items")
				if len(result.Entries) != paths {
					b.Fatalf("unexpected receiver count: %d", len(result.Entries))
				}
			}
		})
	}
}

func BenchmarkArtifactDiscoveryAliases(b *testing.B) {
	for _, variants := range []int{100, 1000} {
		b.Run(fmt.Sprint(variants), func(b *testing.B) {
			all := &Artifacts{}
			for i := range variants {
				dim := &ArtifactDimension{Identifier: fmt.Sprintf("App.items%d", i), Name: "item", QualifiedName: fmt.Sprintf("app-items%d", i)}
				all.Entries = append(all.Entries, &Artifact{Path: []string{"items", "check"}, Node: &ModTreeNode{
					Name: "check", Parent: &ModTreeNode{CollectionDimension: dim, Parent: &ModTreeNode{Name: "items"}},
				}})
			}
			keys := func(context.Context, *Artifact) ([]collectionKey, error) { return []collectionKey{{text: "a"}}, nil }
			b.ReportAllocs()
			for b.Loop() {
				result, err := all.expand(b.Context(), keys)
				if err != nil {
					b.Fatal(err)
				}
				if len(result.Entries) != variants {
					b.Fatal("unexpected item count")
				}
			}
		})
	}
}
