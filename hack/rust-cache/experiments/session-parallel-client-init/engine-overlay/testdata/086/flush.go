package server

import (
	"context"
	"sync"
	"sync/atomic"
)

// telemetryFlushGroup combines overlapping requests without letting a request
// join a flush that started before its telemetry was emitted. A successful
// flush covers only tickets issued before that flush began.
type telemetryFlushGroup struct {
	requested atomic.Uint64
	mu        sync.Mutex
	completed uint64
	active    chan struct{}
}

func (group *telemetryFlushGroup) Do(ctx context.Context, flush func(context.Context) error) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	ticket := group.requested.Add(1)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		group.mu.Lock()
		if group.completed >= ticket {
			group.mu.Unlock()
			return nil
		}
		if group.active != nil {
			done := group.active
			group.mu.Unlock()
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-done:
				continue
			}
		}
		target := group.requested.Load()
		done := make(chan struct{})
		group.active = done
		group.mu.Unlock()

		err := flush(ctx)
		group.mu.Lock()
		if err == nil {
			group.completed = target
		}
		group.active = nil
		close(done)
		group.mu.Unlock()
		return err
	}
}
