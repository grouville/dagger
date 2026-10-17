package metadata

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"os"
	"sort"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/pkg/gc"
	bolt "go.etcd.io/bbolt"
)

func TestDaggerRetainedGraphExport(t *testing.T) {
	root := os.Getenv("DAGGER_GC_GRAPH_ROOT")
	if root == "" {
		t.Skip("requires a copied metadata database")
	}
	db, err := bolt.Open(root+"/containerdmeta.db", 0600, &bolt.Options{ReadOnly: true})
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if err := db.View(func(tx *bolt.Tx) error {
		for err := range tx.Check() {
			t.Fatal(err)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}

	ctx := context.Background()
	c := startGCContext(ctx, nil)
	var roots, marked []gc.Node
	edges := map[gc.Node][]gc.Node{}
	rootCounts := map[gc.Node]int{}
	var scanTime, markTime time.Duration
	calls := 0
	if err := db.View(func(tx *bolt.Tx) error {
		started := time.Now()
		ch := make(chan gc.Node)
		done := make(chan struct{})
		go func() {
			defer close(done)
			for n := range ch {
				roots = append(roots, n)
			}
		}()
		err := c.scanRoots(ctx, tx, ch)
		close(ch)
		<-done
		if err != nil {
			return err
		}
		scanTime = time.Since(started)
		for _, n := range roots {
			rootCounts[n]++
		}
		started = time.Now()
		reachable, err := gc.Tricolor(roots, func(n gc.Node) ([]gc.Node, error) {
			calls++
			var refs []gc.Node
			if err := c.references(ctx, tx, n, func(ref gc.Node) { refs = append(refs, ref) }); err != nil {
				return nil, err
			}
			if _, exists := edges[n]; !exists {
				edges[n] = refs
			}
			return refs, nil
		})
		markTime = time.Since(started)
		for n := range reachable {
			marked = append(marked, n)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
	less := func(a, b gc.Node) bool {
		if a.Type != b.Type {
			return a.Type < b.Type
		}
		if a.Namespace != b.Namespace {
			return a.Namespace < b.Namespace
		}
		return a.Key < b.Key
	}
	type entry struct {
		Node       gc.Node
		References []gc.Node
	}
	entries := make([]entry, 0, len(edges))
	for n, refs := range edges {
		entries = append(entries, entry{n, refs})
	}
	sort.Slice(entries, func(i, j int) bool { return less(entries[i].Node, entries[j].Node) })
	sort.Slice(marked, func(i, j int) bool { return less(marked[i], marked[j]) })
	file, err := os.Create(root + "/retained-graph.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	compressed := gzip.NewWriter(file)
	if err := json.NewEncoder(compressed).Encode(struct {
		Roots   []gc.Node
		Entries []entry
		Marked  []gc.Node
	}{roots, entries, marked}); err != nil {
		t.Fatal(err)
	}
	if err := compressed.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	types := map[gc.ResourceType]int{}
	maxCopies := 0
	for n, count := range rootCounts {
		types[n.Type]++
		if count > maxCopies {
			maxCopies = count
		}
	}
	stats := map[string]any{"roots": len(roots), "unique_roots": len(rootCounts), "unique_roots_by_type": types, "max_root_copies": maxCopies, "reference_calls": calls, "unique_reference_calls": len(edges), "marked": len(marked), "scan_seconds": scanTime.Seconds(), "mark_seconds": markTime.Seconds(), "database_check_passed": true, "collectors": 0}
	data, err := json.MarshalIndent(stats, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(root+"/graph-statistics.json", data, 0600); err != nil {
		t.Fatal(err)
	}
	t.Log(string(data))
}
