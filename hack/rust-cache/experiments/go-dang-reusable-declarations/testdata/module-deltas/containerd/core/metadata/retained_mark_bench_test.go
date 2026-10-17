package metadata

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"maps"
	"os"
	"runtime"
	"testing"

	"github.com/containerd/containerd/v2/pkg/gc"
	bolt "go.etcd.io/bbolt"
)

func retainedGraphOracle(t testing.TB) map[gc.Node]struct{} {
	t.Helper()
	file, err := os.Open(os.Getenv("DAGGER_GC_GRAPH_ROOT") + "/retained-graph.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	compressed, err := gzip.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer compressed.Close()
	var graph struct {
		Roots   []gc.Node
		Entries []struct {
			Node       gc.Node
			References []gc.Node
		}
		Marked []gc.Node
	}
	if err := json.NewDecoder(compressed).Decode(&graph); err != nil {
		t.Fatal(err)
	}
	edges := map[gc.Node][]gc.Node{}
	for _, entry := range graph.Entries {
		edges[entry.Node] = entry.References
	}
	visited, marked := map[gc.Node]bool{}, map[gc.Node]struct{}{}
	queue := append([]gc.Node(nil), graph.Roots...)
	for index := 0; index < len(queue); index++ {
		n := queue[index]
		if visited[n] {
			continue
		}
		visited[n] = true
		queue = append(queue, edges[n]...)
		n.Type &= gc.ResourceMax
		marked[n] = struct{}{}
	}
	exported := map[gc.Node]struct{}{}
	for _, n := range graph.Marked {
		exported[n] = struct{}{}
	}
	if !maps.Equal(exported, marked) {
		t.Fatal("exported result disagrees with independent breadth-first traversal")
	}
	return marked
}

func BenchmarkDaggerRetainedMark(b *testing.B) {
	root := os.Getenv("DAGGER_GC_GRAPH_ROOT")
	if root == "" {
		b.Skip("requires a copied metadata database")
	}
	want := retainedGraphOracle(b)
	db, err := bolt.Open(root+"/containerdmeta.db", 0600, &bolt.Options{ReadOnly: true})
	if err != nil {
		b.Fatal(err)
	}
	defer db.Close()
	metadata := NewDB(db, nil, nil)
	ctx := context.Background()
	var marked map[gc.Node]struct{}
	runtime.GC()
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		marked, err = metadata.getMarked(ctx, startGCContext(ctx, nil))
		if err != nil {
			b.Fatal(err)
		}
	}
	b.StopTimer()
	if !maps.Equal(marked, want) {
		b.Fatal("live result differs from independent captured-graph oracle")
	}
	b.ReportMetric(float64(len(marked)), "retained")
}
