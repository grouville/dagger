package dagql

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// A local-only cache has no receiver for an early snapshot share. Completing
// a result must not wait for an unrelated publication's graph write lock.
func TestSnapshotCompletionWithoutImportsDoesNotWaitForGraph(t *testing.T) {
	c := &Cache{shareAdmission: snapshotShareOn}
	row := &sharedResult{id: 1}
	c.egraphMu.Lock()
	done := make(chan struct{})
	go func() {
		c.notifySnapshotShareCompletion(context.Background(), row)
		close(done)
	}()
	completed := false
	select {
	case <-done:
		completed = true
	case <-time.After(time.Second):
	}
	c.egraphMu.Unlock()
	<-done
	require.True(t, completed, "snapshot completion waited for a graph lock with no imported receiver")
}

func BenchmarkSnapshotCompletionWithoutImports(b *testing.B) {
	c := &Cache{shareAdmission: snapshotShareOn}
	row := &sharedResult{id: 1}
	b.ReportAllocs()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			c.notifySnapshotShareCompletion(context.Background(), row)
		}
	})
}
