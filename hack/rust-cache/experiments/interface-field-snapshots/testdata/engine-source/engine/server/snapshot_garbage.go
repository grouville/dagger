package server

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	ctdmetadata "github.com/containerd/containerd/v2/core/metadata"

	"github.com/dagger/dagger/engine/slog"
	"github.com/dagger/dagger/engine/wcprof"
)

// snapshotGarbage collects snapshot and content data that nothing references
// anymore.
//
// Removing the last lease on a snapshot only marks containerd's metadata DB
// dirty; the data stays on disk until GarbageCollect runs. Leases are removed
// all the time without a prune (session teardown, failed execs, stopped
// services), so pruning alone is not a sufficient trigger: an engine whose
// policies never remove an entry would never reclaim that data. Instead the
// engine records pending deletions here and collects them on its regular GC
// passes.
type snapshotGarbage struct {
	db      *ctdmetadata.DB
	pending atomic.Bool
	// Diagnostic fields; production behavior is the zero value.
	deferred         atomic.Bool
	diagnosticMu     sync.Mutex
	diagnosticEvents []snapshotCollectionEvent
}

func newSnapshotGarbage(db *ctdmetadata.DB) *snapshotGarbage {
	g := &snapshotGarbage{db: db}
	// containerd counts deletions in memory only, so garbage left by a
	// previous engine process is invisible to it. Collect once regardless.
	g.pending.Store(true)
	db.RegisterMutationCallback(func(dirty bool) {
		// This runs on the DB's write path while it holds the lock that
		// GarbageCollect needs, so only record the signal here.
		if dirty {
			g.pending.Store(true)
		}
	})
	return g
}

// Collect runs containerd garbage collection unconditionally.
func (g *snapshotGarbage) Collect(ctx context.Context) error {
	if g.deferred.Load() {
		started := time.Now()
		g.pending.Store(true)
		g.recordCollection(snapshotCollectionEvent{Start: started, End: time.Now(), Deferred: true})
		return nil
	}
	return g.collect(ctx)
}

// collect also permits the diagnostic controller to force one collection while
// ordinary background collections are deferred. It never drops cache roots.
func (g *snapshotGarbage) collect(ctx context.Context) (rerr error) {
	started := time.Now()
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "snapshot.collect", wcprof.OpOpts{})
	defer func() {
		op.EndErr(rerr)
		event := snapshotCollectionEvent{Start: started, End: time.Now()}
		if rerr != nil {
			event.Error = rerr.Error()
		}
		g.recordCollection(event)
	}()
	// Clear before collecting: a deletion that lands during the collection
	// sets the flag again and is picked up by the next pass.
	g.pending.Store(false)
	stats, err := g.db.GarbageCollect(ctx)
	if err != nil {
		g.pending.Store(true)
		return err
	}
	slog.Debug("collected snapshot garbage", "stats", stats)
	return nil
}

// CollectIfPending runs garbage collection if anything was deleted since the
// last collection.
func (g *snapshotGarbage) CollectIfPending(ctx context.Context) error {
	if g == nil || !g.pending.Load() {
		return nil
	}
	return g.Collect(ctx)
}

type snapshotCollectionEvent struct {
	Start    time.Time `json:"start"`
	End      time.Time `json:"end"`
	Deferred bool      `json:"deferred"`
	Error    string    `json:"error,omitempty"`
}

func (g *snapshotGarbage) recordCollection(event snapshotCollectionEvent) {
	g.diagnosticMu.Lock()
	defer g.diagnosticMu.Unlock()
	if len(g.diagnosticEvents) == 256 {
		copy(g.diagnosticEvents, g.diagnosticEvents[1:])
		g.diagnosticEvents = g.diagnosticEvents[:255]
	}
	g.diagnosticEvents = append(g.diagnosticEvents, event)
}
func (g *snapshotGarbage) diagnosticState() map[string]any {
	g.diagnosticMu.Lock()
	events := append([]snapshotCollectionEvent(nil), g.diagnosticEvents...)
	g.diagnosticMu.Unlock()
	return map[string]any{"deferred": g.deferred.Load(), "pending": g.pending.Load(), "events": events}
}
