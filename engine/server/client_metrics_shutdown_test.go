package server

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	metricapi "go.opentelemetry.io/otel/metric"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

// The real PeriodicReader is essential: a fake provider would only assert the
// implementation's choice of methods, not final metric delivery and collection.
type finalCollectionExporter struct {
	mu            sync.Mutex
	values        []int64
	shutdownCalls int
	export        func(context.Context) error
	shutdownError error
}

func (*finalCollectionExporter) Temporality(sdkmetric.InstrumentKind) metricdata.Temporality {
	return metricdata.CumulativeTemporality
}

func (*finalCollectionExporter) Aggregation(kind sdkmetric.InstrumentKind) sdkmetric.Aggregation {
	return sdkmetric.DefaultAggregationSelector(kind)
}

func (e *finalCollectionExporter) Export(ctx context.Context, metrics *metricdata.ResourceMetrics) error {
	e.mu.Lock()
	for _, scope := range metrics.ScopeMetrics {
		for _, metric := range scope.Metrics {
			if metric.Name != "test.final.value" {
				continue
			}
			if gauge, ok := metric.Data.(metricdata.Gauge[int64]); ok {
				for _, point := range gauge.DataPoints {
					e.values = append(e.values, point.Value)
				}
			}
		}
	}
	e.mu.Unlock()
	if e.export != nil {
		return e.export(ctx)
	}
	return nil
}

func (*finalCollectionExporter) ForceFlush(context.Context) error { return nil }

func (e *finalCollectionExporter) Shutdown(context.Context) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.shutdownCalls++
	return e.shutdownError
}

func (e *finalCollectionExporter) snapshot() ([]int64, int) {
	e.mu.Lock()
	defer e.mu.Unlock()
	return append([]int64(nil), e.values...), e.shutdownCalls
}

func finalCollectionClient(t *testing.T, exporters ...*finalCollectionExporter) (*clientRuntime, *atomic.Int64, *atomic.Int64) {
	t.Helper()
	opts := make([]sdkmetric.Option, 0, len(exporters))
	for _, exporter := range exporters {
		opts = append(opts, sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exporter, sdkmetric.WithInterval(time.Hour))))
	}
	provider := sdkmetric.NewMeterProvider(opts...)
	t.Cleanup(func() { _ = provider.Shutdown(context.Background()) })
	var value, collections atomic.Int64
	_, err := provider.Meter("test").Int64ObservableGauge("test.final.value", metricapi.WithInt64Callback(func(_ context.Context, observer metricapi.Int64Observer) error {
		collections.Add(1)
		observer.Observe(value.Load())
		return nil
	}))
	require.NoError(t, err)
	client := &clientRuntime{meterProvider: provider}
	client.telemetryDebug.MeterProviders = 1
	client.telemetryDebug.ConfiguredMetricReaders = len(exporters)
	return client, &value, &collections
}

func TestClientShutdownMetricsCollectsEachReaderOnce(t *testing.T) {
	t.Parallel()
	local, cloud := &finalCollectionExporter{}, &finalCollectionExporter{}
	client, value, collections := finalCollectionClient(t, local, cloud)
	value.Store(42)
	require.NoError(t, client.shutdownMetrics(t.Context()))
	for _, exporter := range []*finalCollectionExporter{local, cloud} {
		values, shutdowns := exporter.snapshot()
		require.Equal(t, []int64{42}, values, "the final value must reach each real reader exactly once")
		require.Equal(t, 1, shutdowns)
	}
	require.Equal(t, int64(2), collections.Load(), "one callback invocation per reader")
	require.Nil(t, client.meterProvider)
	require.Nil(t, client.metricExporter)
	require.Zero(t, client.telemetryDebug.MeterProviders)
	require.Zero(t, client.telemetryDebug.ConfiguredMetricReaders)
	require.NoError(t, client.shutdownMetrics(t.Context()))
	require.Equal(t, int64(2), collections.Load(), "quiescent reclamation remains idempotent")
}

func TestClientShutdownMetricsPreservesFinalUpdateAfterExplicitFlush(t *testing.T) {
	t.Parallel()
	exporter := &finalCollectionExporter{}
	client, value, collections := finalCollectionClient(t, exporter)
	value.Store(41)
	require.NoError(t, client.flushMetrics(t.Context()))
	value.Store(42)
	require.NoError(t, client.shutdownMetrics(t.Context()))
	values, shutdowns := exporter.snapshot()
	require.Equal(t, []int64{41, 42}, values, "a real explicit flush must not suppress later cleanup values")
	require.Equal(t, int64(2), collections.Load())
	require.Equal(t, 1, shutdowns)
}

func TestClientShutdownMetricsWaitsForFinalExportAndHonorsCancellation(t *testing.T) {
	t.Parallel()
	entered := make(chan struct{})
	var enteredOnce sync.Once
	exporter := &finalCollectionExporter{export: func(ctx context.Context) error {
		enteredOnce.Do(func() { close(entered) })
		<-ctx.Done()
		return ctx.Err()
	}}
	client, value, _ := finalCollectionClient(t, exporter)
	value.Store(42)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- client.shutdownMetrics(ctx) }()
	select {
	case <-entered:
	case <-t.Context().Done():
		t.Fatal("final export was not started")
	}
	select {
	case err := <-done:
		t.Fatalf("shutdown returned before final export completed: %v", err)
	default:
	}
	cancel()
	select {
	case err := <-done:
		require.ErrorIs(t, err, context.Canceled)
	case <-t.Context().Done():
		t.Fatal("shutdown did not join its canceled final export")
	}
	_, shutdowns := exporter.snapshot()
	require.Equal(t, 1, shutdowns)
	require.Nil(t, client.meterProvider)
}

func TestClientShutdownMetricsReturnsFinalCollectionErrorAndReleasesReader(t *testing.T) {
	t.Parallel()
	want := errors.New("final metric callback failed")
	exporter := &finalCollectionExporter{}
	provider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exporter, sdkmetric.WithInterval(time.Hour))))
	t.Cleanup(func() { _ = provider.Shutdown(context.Background()) })
	_, err := provider.Meter("test").Int64ObservableGauge("test.final.value", metricapi.WithInt64Callback(func(context.Context, metricapi.Int64Observer) error { return want }))
	require.NoError(t, err)
	client := &clientRuntime{meterProvider: provider}
	require.ErrorIs(t, client.shutdownMetrics(t.Context()), want)
	_, shutdowns := exporter.snapshot()
	require.Equal(t, 1, shutdowns)
	require.Nil(t, client.meterProvider)
}

func TestClientShutdownMetricsFailureStillClosesBothReaders(t *testing.T) {
	t.Parallel()
	firstErr := errors.New("first reader export failed")
	secondErr := errors.New("second reader shutdown failed")
	first := &finalCollectionExporter{export: func(context.Context) error { return firstErr }}
	second := &finalCollectionExporter{shutdownError: secondErr}
	client, value, _ := finalCollectionClient(t, first, second)
	value.Store(42)
	err := client.shutdownMetrics(t.Context())
	require.ErrorIs(t, err, firstErr)
	require.ErrorIs(t, err, secondErr, "MeterProvider joins errors from both readers without short-circuiting")
	for _, exporter := range []*finalCollectionExporter{first, second} {
		values, shutdowns := exporter.snapshot()
		require.Equal(t, []int64{42}, values)
		require.Equal(t, 1, shutdowns)
	}
	require.Nil(t, client.meterProvider)
}

func TestClientShutdownMetricsCancellationStillClosesSecondReader(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	first := &finalCollectionExporter{export: func(context.Context) error {
		cancel()
		return context.Canceled
	}}
	// The pinned PeriodicReader returns the earlier collection/context error
	// in preference to an exporter Shutdown error. Removing a preceding flush
	// must not prevent the second exporter's cleanup from being called.
	second := &finalCollectionExporter{shutdownError: errors.New("later shutdown error")}
	client, value, _ := finalCollectionClient(t, first, second)
	value.Store(42)
	require.ErrorIs(t, client.shutdownMetrics(ctx), context.Canceled)
	for _, exporter := range []*finalCollectionExporter{first, second} {
		_, shutdowns := exporter.snapshot()
		require.Equal(t, 1, shutdowns)
	}
	require.Nil(t, client.meterProvider)
	require.NoError(t, client.shutdownMetrics(t.Context()))
}
