package server

import (
	"context"
	"sync"
	"testing"
	"time"

	enginetel "github.com/dagger/dagger/engine/telemetry"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

type canceledSessionSpanExporter struct {
	started, stopped chan struct{}
	start, stop      sync.Once
}

func (e *canceledSessionSpanExporter) ExportSpans(ctx context.Context, _ []sdktrace.ReadOnlySpan) error {
	e.start.Do(func() { close(e.started) })
	<-ctx.Done()
	e.stop.Do(func() { close(e.stopped) })
	return ctx.Err()
}

func (*canceledSessionSpanExporter) Shutdown(context.Context) error { return nil }

// Signal when the session reaches its trace drain, whether it first flushes
// or shuts down. Canceling there models a drain exhausting its deadline.
type sessionDrainSpanProcessor struct {
	sdktrace.SpanProcessor
	entered chan struct{}
	once    sync.Once
}

func (p *sessionDrainSpanProcessor) ForceFlush(ctx context.Context) error {
	p.once.Do(func() { close(p.entered) })
	return p.SpanProcessor.ForceFlush(ctx)
}

func (p *sessionDrainSpanProcessor) Shutdown(ctx context.Context) error {
	p.once.Do(func() { close(p.entered) })
	return p.SpanProcessor.Shutdown(ctx)
}

func TestSessionTelemetryShutdownStopsExportAfterDrainCancellation(t *testing.T) {
	exporter := &canceledSessionSpanExporter{started: make(chan struct{}), stopped: make(chan struct{})}
	processor := enginetel.NewCallSpanProcessor(exporter)
	t.Cleanup(func() {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		_ = processor.Shutdown(ctx)
	})
	probe := &sessionDrainSpanProcessor{SpanProcessor: processor, entered: make(chan struct{})}
	sess := &daggerSession{tracerProvider: sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(probe))}
	processor.OnEnd(callSpan(t, "main", 1, []byte("frame"), "xxh3:shutdown"))
	select {
	case <-exporter.started:
	case <-time.After(5 * time.Second):
		t.Fatal("background export did not start")
	}

	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- sess.shutdownTelemetry(ctx) }()
	select {
	case <-probe.entered:
	case <-time.After(5 * time.Second):
		t.Fatal("session did not start draining traces")
	}
	cancel()
	select {
	case err := <-done:
		require.ErrorIs(t, err, context.Canceled)
	case <-time.After(5 * time.Second):
		t.Fatal("session telemetry shutdown did not return")
	}
	select {
	case <-exporter.stopped:
	default:
		t.Fatal("background span export outlived session telemetry shutdown")
	}
}
