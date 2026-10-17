package server

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"sync/atomic"
	"testing"
	"testing/synctest"

	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/log"
)

func TestTelemetryFlushGroupCoversEmissionsDuringFlush(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var group telemetryFlushGroup
		var emitted, delivered, calls atomic.Int64
		started, release := make(chan struct{}), make(chan struct{})
		results := make(chan error, 33)
		flush := func(context.Context) error {
			captured := emitted.Load()
			if calls.Add(1) == 1 {
				close(started)
				<-release
			}
			delivered.Store(captured)
			return nil
		}
		request := func() {
			lastEmission := emitted.Add(1)
			err := group.Do(context.Background(), flush)
			if err == nil && delivered.Load() < lastEmission {
				err = fmt.Errorf("returned before emission %d was delivered", lastEmission)
			}
			results <- err
		}
		go request()
		<-started
		for range 32 {
			go request()
		}
		synctest.Wait()
		require.EqualValues(t, 33, group.requested.Load(), "all requests must be waiting behind the first pass")
		require.Empty(t, results)
		close(release)
		synctest.Wait()
		for range 33 {
			require.NoError(t, <-results)
		}
		require.EqualValues(t, 2, calls.Load(), "the later emissions require one more pass, not 32")
		// A later caller cannot reuse an earlier successful flush.
		request()
		require.NoError(t, <-results)
		require.EqualValues(t, 3, calls.Load())
	})
}

func TestTelemetryFlushGroupRetriesFailure(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var group telemetryFlushGroup
		failure := errors.New("export failed")
		started, release := make(chan struct{}), make(chan struct{})
		first, second := make(chan error, 1), make(chan error, 1)
		go func() {
			first <- group.Do(context.Background(), func(context.Context) error {
				close(started)
				<-release
				return failure
			})
		}()
		<-started
		var retried atomic.Bool
		go func() {
			second <- group.Do(context.Background(), func(context.Context) error {
				retried.Store(true)
				return nil
			})
		}()
		synctest.Wait()
		close(release)
		synctest.Wait()
		require.ErrorIs(t, <-first, failure)
		require.NoError(t, <-second)
		require.True(t, retried.Load(), "a failed pass cannot satisfy another caller")
	})
}

func TestTelemetryFlushGroupWaitingCancellation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var group telemetryFlushGroup
		started, release := make(chan struct{}), make(chan struct{})
		first, second := make(chan error, 1), make(chan error, 1)
		go func() {
			first <- group.Do(context.Background(), func(context.Context) error {
				close(started)
				<-release
				return nil
			})
		}()
		<-started
		ctx, cancel := context.WithCancel(context.Background())
		go func() {
			second <- group.Do(ctx, func(context.Context) error {
				t.Error("canceled waiter started a flush")
				return nil
			})
		}()
		synctest.Wait()
		cancel()
		synctest.Wait()
		require.ErrorIs(t, <-second, context.Canceled)
		require.Empty(t, first, "canceling a waiter must not cancel the active flush")
		close(release)
		synctest.Wait()
		require.NoError(t, <-first)
	})
}

func TestTelemetryFlushGroupActiveCancellation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var group telemetryFlushGroup
		started := make(chan struct{})
		first, second := make(chan error, 1), make(chan error, 1)
		ctx, cancel := context.WithCancel(context.Background())
		go func() {
			first <- group.Do(ctx, func(ctx context.Context) error {
				close(started)
				<-ctx.Done()
				return ctx.Err()
			})
		}()
		<-started
		go func() {
			second <- group.Do(context.Background(), func(context.Context) error { return nil })
		}()
		synctest.Wait()
		cancel()
		synctest.Wait()
		require.ErrorIs(t, <-first, context.Canceled)
		require.NoError(t, <-second, "an uncanceled waiter must be able to retry")
	})
}

func TestSessionCoalescedFlushDeliversSignals(t *testing.T) {
	saved := telemetryFlushCoalescingEnabled.Load()
	telemetryFlushCoalescingEnabled.Store(false)
	t.Cleanup(func() { telemetryFlushCoalescingEnabled.Store(saved) })
	receiver := newCloudReceiver(t, false)
	srv := &Server{}
	sess, root := newCloudTestSession(t, srv, &engine.ClientMetadata{
		CloudAuth: basicCloudAuth("dag_test_token"), CloudURL: receiver.URL,
		CloudTelemetryPublisher: engine.CloudTelemetryPublisherEngine,
	})
	ctx := engine.ContextWithClientMetadata(t.Context(), root.clientMetadata)
	counter, err := root.meterProvider.Meter("test").Int64Counter("coalesced.metric")
	require.NoError(t, err)
	results := make(chan error, 16)
	for i := range 16 {
		go func() {
			name := fmt.Sprintf("coalesced-%d", i)
			spanCtx, span := sess.tracerProvider.Tracer("test").Start(ctx, name)
			span.SetAttributes(attribute.String("test.record", name))
			span.End()
			var rec log.Record
			rec.SetBody(log.StringValue(name))
			sess.loggerProvider.Logger("test").Emit(spanCtx, rec)
			counter.Add(ctx, 1)
			results <- sess.FlushTelemetry(ctx, "concurrent test")
		}()
	}
	for range 16 {
		require.NoError(t, <-results)
	}
	sess.flushSessionCloudTelemetry(ctx)
	publishRestToCloud(ctx, t, sess)
	_, spans, logs, metrics := receiver.snapshot()
	for i := range 16 {
		name := fmt.Sprintf("coalesced-%d", i)
		require.True(t, slices.Contains(spans, name), "missing span %s", name)
		require.True(t, slices.Contains(logs, name), "missing log %s", name)
	}
	require.Contains(t, metrics, "coalesced.metric")
}
