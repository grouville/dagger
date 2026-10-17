// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

package trace

import (
	"context"
	"fmt"
	"slices"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	oteltrace "go.opentelemetry.io/otel/trace"
)

// Check observable FIFO behavior against a simple reference, including copies
// taken before and after multiple wraps. These tests also run on the original.
func TestEvictedQueueRetainedValues(t *testing.T) {
	for _, capacity := range []int{-1, 0, 1, 3, 128} {
		t.Run(fmt.Sprint(capacity), func(t *testing.T) {
			q := newEvictedQueueEvent(capacity)
			var expected []Event
			var oldCopies [][]Event
			var expectedCopies [][]Event
			const total = 521
			for i := range total {
				value := Event{Name: fmt.Sprint(i)}
				q.add(value)
				if capacity != 0 {
					expected = append(expected, value)
					if capacity > 0 && len(expected) > capacity {
						expected = slices.Clone(expected[len(expected)-capacity:])
					}
				}
				require.Equal(t, expected, q.copy(), "after adding %d", i)
				require.Equal(t, i+1-len(expected), q.droppedCount)
				if i%37 == 0 {
					oldCopies = append(oldCopies, q.copy())
					expectedCopies = append(expectedCopies, slices.Clone(expected))
				}
			}
			require.Equal(t, expectedCopies, oldCopies, "later writes changed an earlier snapshot")
			if copy := q.copy(); len(copy) > 0 {
				copy[0].Name = "mutated snapshot"
				require.Equal(t, expected, q.copy(), "snapshot mutation changed the queue")
			}
		})
	}
}

func TestEvictedQueueSpanSnapshots(t *testing.T) {
	limits := NewSpanLimits()
	limits.LinkCountLimit = 3
	limits.EventCountLimit = 3
	tp := NewTracerProvider(WithRawSpanLimits(limits))
	t.Cleanup(func() { require.NoError(t, tp.Shutdown(context.Background())) })
	_, span := tp.Tracer("queue-test").Start(t.Context(), "test")
	ro := span.(ReadOnlySpan)
	for i := range 8 {
		span.AddLink(oteltrace.Link{Attributes: []attribute.KeyValue{attribute.Int("index", i)}})
		span.AddEvent(fmt.Sprint(i))
	}
	links, events := ro.Links(), ro.Events()
	for i := range 3 {
		require.Equal(t, int64(i+5), links[i].Attributes[0].Value.AsInt64())
		require.Equal(t, fmt.Sprint(i+5), events[i].Name)
	}
	span.AddEvent("last")
	span.AddLink(oteltrace.Link{Attributes: []attribute.KeyValue{attribute.Int("index", 8)}})
	require.Equal(t, "5", events[0].Name)
	require.Equal(t, int64(5), links[0].Attributes[0].Value.AsInt64())
	span.End()
	final := span.(*recordingSpan).snapshot()
	require.Equal(t, ro.Links(), final.Links())
	require.Equal(t, ro.Events(), final.Events())
	require.Equal(t, 6, final.DroppedLinks())
	require.Equal(t, 6, final.DroppedEvents())
}

func TestEvictedQueueConcurrentSpanUpdates(t *testing.T) {
	limits := NewSpanLimits()
	limits.LinkCountLimit = 128
	tp := NewTracerProvider(WithRawSpanLimits(limits))
	t.Cleanup(func() { require.NoError(t, tp.Shutdown(context.Background())) })
	_, span := tp.Tracer("queue-test").Start(t.Context(), "concurrent")
	var wg sync.WaitGroup
	for worker := range 8 {
		wg.Go(func() {
			for item := range 64 {
				span.AddLink(oteltrace.Link{Attributes: []attribute.KeyValue{
					attribute.Int("index", worker*64+item),
				}})
				_ = span.(ReadOnlySpan).Links()
			}
		})
	}
	wg.Wait()
	span.End()
	result := span.(*recordingSpan).snapshot()
	require.Len(t, result.Links(), 128)
	require.Equal(t, 8*64-128, result.DroppedLinks())
	seen := make(map[int64]bool)
	for _, link := range result.Links() {
		index := link.Attributes[0].Value.AsInt64()
		require.False(t, seen[index], "duplicate retained link %d", index)
		seen[index] = true
	}
}

func BenchmarkEvictedQueueFull(b *testing.B) {
	for _, capacity := range []int{128, 16384} {
		b.Run(fmt.Sprint(capacity), func(b *testing.B) {
			q := newEvictedQueueLink(capacity)
			link := Link{Attributes: []attribute.KeyValue{attribute.String("purpose", "wait")}}
			for range capacity {
				q.add(link)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				q.add(link)
			}
		})
	}
}

func BenchmarkEvictedQueueBatchSnapshot(b *testing.B) {
	for _, capacity := range []int{128, 16384} {
		b.Run(fmt.Sprint(capacity), func(b *testing.B) {
			q := newEvictedQueueLink(capacity)
			link := Link{Attributes: []attribute.KeyValue{attribute.String("purpose", "wait")}}
			for range capacity {
				q.add(link)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				for range 128 {
					q.add(link)
				}
				if len(q.copy()) != capacity {
					b.Fatal("snapshot length changed")
				}
			}
		})
	}
}

func BenchmarkEvictedQueueSnapshot(b *testing.B) {
	for _, capacity := range []int{128, 16384} {
		for _, dropped := range []int{0, 1, 127} {
			b.Run(fmt.Sprintf("%d/drop%d", capacity, dropped), func(b *testing.B) {
				q := newEvictedQueueLink(capacity)
				for range capacity + dropped {
					q.add(Link{})
				}
				b.ReportAllocs()
				b.ResetTimer()
				for b.Loop() {
					if len(q.copy()) != capacity {
						b.Fatal("snapshot length changed")
					}
				}
			})
		}
	}
}

func BenchmarkEvictedQueueShortSpan(b *testing.B) {
	for _, capacity := range []int{128, 16384} {
		b.Run(fmt.Sprint(capacity), func(b *testing.B) {
			link := Link{Attributes: []attribute.KeyValue{attribute.String("purpose", "wait")}}
			b.ReportAllocs()
			for b.Loop() {
				q := newEvictedQueueLink(capacity)
				for range 8 {
					q.add(link)
				}
				if len(q.copy()) != 8 {
					b.Fatal("snapshot length changed")
				}
			}
		})
	}
}

func BenchmarkSpanAddLinkFull(b *testing.B) {
	for _, capacity := range []int{128, 16384} {
		b.Run(fmt.Sprint(capacity), func(b *testing.B) {
			limits := NewSpanLimits()
			limits.LinkCountLimit = capacity
			tp := NewTracerProvider(WithRawSpanLimits(limits))
			b.Cleanup(func() { _ = tp.Shutdown(context.Background()) })
			_, span := tp.Tracer("queue-benchmark").Start(b.Context(), "full")
			link := oteltrace.Link{Attributes: []attribute.KeyValue{
				attribute.String("dagger.io/link.purpose", "wait"),
				attribute.String("dagger.io/wcprof.wait.reason", "call_exec"),
				attribute.String("dagger.io/wcprof.wait.start_unix_nano", "1792220000000000000"),
				attribute.String("dagger.io/wcprof.wait.end_unix_nano", "1792220000000010000"),
			}}
			for range capacity {
				span.AddLink(link)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				span.AddLink(link)
			}
			span.End()
		})
	}
}
