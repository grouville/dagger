package core

import (
	"fmt"
	"testing"
)

func BenchmarkArtifactDimensionKeys(b *testing.B) {
	for _, count := range []int{1, 10, 100, 1000} {
		b.Run(fmt.Sprintf("collections=%d", count), func(b *testing.B) {
			all := &Artifacts{}
			dimension := &ArtifactDimension{Identifier: "app/items", Name: "item"}
			for i := range count {
				path := []string{fmt.Sprintf("collection%d", i)}
				item := &ModTreeNode{Name: "get", CollectionDimension: dimension}
				all.Entries = append(all.Entries,
					&Artifact{Path: path, Node: item, TypeName: "Item"},
					&Artifact{Path: append([]string{}, path...), Node: &ModTreeNode{Parent: item, Name: "check"}, TypeName: "Check"},
				)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				selected := all.ForDimensionKeys(dimension.Identifier)
				if len(selected.Entries) != len(all.Entries) {
					b.Fatal("different types at the same path and dimension must remain selected")
				}
			}
		})
	}
}
