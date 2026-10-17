// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

package trace // import "go.opentelemetry.io/otel/sdk/trace"

import (
	"slices"
	"sync"

	"go.opentelemetry.io/otel/internal/global"
)

// evictedQueue is a FIFO queue with a configurable capacity.
type evictedQueue[T any] struct {
	queue          []T
	head           int
	ring           bool
	capacity       int
	droppedCount   int
	logDroppedMsg  string
	logDroppedOnce sync.Once
}

func newEvictedQueueEvent(capacity int) evictedQueue[Event] {
	// Do not pre-allocate queue, do this lazily.
	return evictedQueue[Event]{
		capacity:      capacity,
		ring:          evictedQueueRingDiagnostic.Load(),
		logDroppedMsg: "limit reached: dropping trace trace.Event",
	}
}

func newEvictedQueueLink(capacity int) evictedQueue[Link] {
	// Do not pre-allocate queue, do this lazily.
	return evictedQueue[Link]{
		capacity:      capacity,
		ring:          evictedQueueRingDiagnostic.Load(),
		logDroppedMsg: "limit reached: dropping trace trace.Link",
	}
}

// add adds value to the evictedQueue eq. If eq is at capacity, the oldest
// queued value will be discarded and the drop count incremented.
func (eq *evictedQueue[T]) add(value T) {
	if !eq.ring {
		eq.addOriginal(value)
		return
	}
	eq.addRing(value)
}

func (eq *evictedQueue[T]) addRing(value T) {
	if eq.capacity == 0 {
		eq.droppedCount++
		eq.logDropped()
		return
	}

	if eq.capacity > 0 && len(eq.queue) == eq.capacity {
		// Replace the oldest value without shifting the retained values.
		eq.queue[eq.head] = value
		eq.head++
		if eq.head == len(eq.queue) {
			eq.head = 0
		}
		eq.droppedCount++
		eq.logDropped()
		return
	}
	eq.queue = append(eq.queue, value)
}

func (eq *evictedQueue[T]) logDropped() {
	eq.logDroppedOnce.Do(func() { global.Warn(eq.logDroppedMsg) })
}

// copy returns a copy of the evictedQueue.
func (eq *evictedQueue[T]) copy() []T {
	if eq.head == 0 {
		return slices.Clone(eq.queue)
	}
	queue := make([]T, len(eq.queue))
	n := copy(queue, eq.queue[eq.head:])
	copy(queue[n:], eq.queue[:eq.head])
	return queue
}

func (eq *evictedQueue[T]) addOriginal(value T) {
	if eq.capacity == 0 {
		eq.droppedCount++
		eq.logDropped()
		return
	}

	if eq.capacity > 0 && len(eq.queue) == eq.capacity {
		// Drop first-in while avoiding allocating more capacity to eq.queue.
		copy(eq.queue[:eq.capacity-1], eq.queue[1:])
		eq.queue = eq.queue[:eq.capacity-1]
		eq.droppedCount++
		eq.logDropped()
	}
	eq.queue = append(eq.queue, value)
}
