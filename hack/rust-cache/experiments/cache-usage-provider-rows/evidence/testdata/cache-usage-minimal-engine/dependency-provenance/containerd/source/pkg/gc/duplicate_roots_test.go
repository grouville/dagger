package gc

import (
	"fmt"
	"maps"
	"slices"
	"testing"
)

func TestTricolorDuplicateRoots(t *testing.T) {
	old := RootDedupDiagnosticEnabled()
	SetRootDedupDiagnostic(true)
	defer SetRootDedupDiagnostic(old)
	a := Node{Type: 1, Namespace: "first", Key: "root"}
	flat := a
	flat.Type |= ResourceMax + 1
	other := a
	other.Namespace = "second"
	child := Node{Type: 2, Namespace: "first", Key: "child"}
	leaf := Node{Type: 2, Namespace: "second", Key: "leaf"}
	graph := map[Node][]Node{a: {child}, flat: {leaf}, other: {a}, child: {a}}
	roots := []Node{a, flat, a, other, flat, other}
	original := slices.Clone(roots)
	calls := map[Node]int{}
	marked, err := Tricolor(roots, func(n Node) ([]Node, error) {
		calls[n]++
		return graph[n], nil
	})
	if err != nil {
		t.Fatal(err)
	}
	want := map[Node]struct{}{a: {}, other: {}, child: {}, leaf: {}}
	if !maps.Equal(marked, want) {
		t.Fatalf("marked %v; want %v", marked, want)
	}
	for n, count := range calls {
		if count != 1 {
			t.Errorf("references for %v visited %d times; want once", n, count)
		}
	}
	if !slices.Equal(roots, original) {
		t.Fatal("modified input roots")
	}
}

func BenchmarkTricolorUniqueRoots(b *testing.B) {
	for _, count := range []int{1, 1000} {
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			roots := make([]Node, count)
			for i := range roots {
				roots[i] = Node{Key: fmt.Sprint(i)}
			}
			refs := func(Node) ([]Node, error) { return nil, nil }
			b.ReportAllocs()
			b.ResetTimer()
			for range b.N {
				marked, err := Tricolor(roots, refs)
				if err != nil || len(marked) != count {
					b.Fatal("incorrect mark result", err)
				}
			}
		})
	}
}
