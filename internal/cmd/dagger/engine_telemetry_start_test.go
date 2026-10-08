package daggercmd

import (
	"context"
	"slices"
	"sync"
	"testing"
	"time"

	telemetry "github.com/dagger/otel-go"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

type firstCloudExport struct {
	*tracetest.InMemoryExporter
	started chan []sdktrace.ReadOnlySpan
	release chan struct{}
	once    sync.Once
}

func (e *firstCloudExport) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {
	e.once.Do(func() { e.started <- slices.Clone(spans) })
	select {
	case <-e.release:
	case <-ctx.Done():
		return ctx.Err()
	}
	return e.InMemoryExporter.ExportSpans(ctx, spans)
}

// Retain exported spans for assertions after the provider shuts down.
func (*firstCloudExport) Shutdown(context.Context) error { return nil }

func TestStartCloudTraceExportPreservesFinalSpans(t *testing.T) {
	exporter := &firstCloudExport{
		InMemoryExporter: tracetest.NewInMemoryExporter(),
		started:          make(chan []sdktrace.ReadOnlySpan, 1),
		release:          make(chan struct{}),
	}
	processor := &telemetry.LiveSpanProcessor{SpanProcessor: sdktrace.NewBatchSpanProcessor(
		telemetry.CoalescingSpanExporter{SpanExporter: exporter},
		// Export must start without waiting for this interval or shutdown.
		sdktrace.WithBatchTimeout(time.Hour),
	)}
	provider := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(processor))
	var releaseOnce sync.Once
	release := func() { releaseOnce.Do(func() { close(exporter.release) }) }
	t.Cleanup(func() {
		release()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = provider.Shutdown(ctx)
	})

	ctx, cancel := context.WithCancel(t.Context())
	ctx, root := provider.Tracer("test").Start(ctx, "command")
	cancel()
	// Cancellation of the command must not cancel delivery of its trace.
	startCloudTraceExport(ctx, processor)

	select {
	case spans := <-exporter.started:
		require.Len(t, spans, 1)
		require.Equal(t, "command", spans[0].Name())
		require.True(t, spans[0].EndTime().Before(spans[0].StartTime()), "the first export contains the live command")
	case <-time.After(5 * time.Second):
		t.Fatal("the first export waited for the batch interval")
	}

	// Command work can finish while the first request is still blocked.
	_, child := provider.Tracer("test").Start(ctx, "build")
	child.End()
	root.End()
	release()
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	require.NoError(t, provider.Shutdown(shutdownCtx))

	finished := map[string]bool{}
	for _, span := range exporter.GetSpans() {
		if span.EndTime.After(span.StartTime) {
			finished[span.Name] = true
		}
	}
	require.Equal(t, map[string]bool{"command": true, "build": true}, finished)
}
