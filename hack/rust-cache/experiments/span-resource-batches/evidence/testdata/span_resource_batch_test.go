package server

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/dagger/dagger/engine/clientdb"
	telemetry "github.com/dagger/otel-go"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/protobuf/encoding/protojson"
)

func resourceBatchSpan(id int, res *resource.Resource) sdktrace.ReadOnlySpan {
	return tracetest.SpanStub{
		Name:        fmt.Sprintf("work-%d", id),
		SpanContext: trace.NewSpanContext(trace.SpanContextConfig{TraceID: trace.TraceID{1}, SpanID: trace.SpanID{byte(id >> 8), byte(id)}}),
		StartTime:   time.Unix(1, 0),
		EndTime:     time.Unix(2, 0),
		Resource:    res,
	}.Snapshot()
}

func TestSpanResourceBatch(t *testing.T) {
	dbs := clientdb.NewDBs(t.TempDir())
	t.Cleanup(func() { require.NoError(t, dbs.Close()) })
	ps := &PubSub{srv: &Server{clientDBs: dbs}}
	a := resource.NewSchemaless(attribute.String("service.name", "engine"), attribute.String("session", "one"))
	b := resource.NewSchemaless(attribute.String("service.name", "engine"), attribute.String("session", "two"))
	bad := resource.NewSchemaless(attribute.String("invalid", "\xff"))
	batches := [][]*resource.Resource{{a, a, b, a, nil, b, bad, bad, a}, {b, nil, a}}
	var expected []*resource.Resource
	nextID := 1
	for _, batch := range batches {
		var spans []sdktrace.ReadOnlySpan
		for _, res := range batch {
			spans = append(spans, resourceBatchSpan(nextID, res))
			nextID++
		}
		require.NoError(t, ps.Spans("client").ExportSpans(t.Context(), spans))
		for _, res := range batch {
			if res != bad {
				expected = append(expected, res)
			}
		}
	}
	db, err := dbs.Open(t.Context(), "client")
	require.NoError(t, err)
	defer db.Close()
	rows, err := db.SelectSpansSince(t.Context(), clientdb.SelectSpansSinceParams{Limit: 100})
	require.NoError(t, err)
	require.Len(t, rows, len(expected))
	for i, res := range expected {
		want, err := protojson.Marshal(telemetry.ResourcePtrToPB(res))
		require.NoError(t, err)
		require.JSONEq(t, string(want), string(rows[i].Resource), "row %d", i)
	}
}

func TestSpanResourceBatchConcurrentExports(t *testing.T) {
	dbs := clientdb.NewDBs(t.TempDir())
	t.Cleanup(func() { require.NoError(t, dbs.Close()) })
	ps := &PubSub{srv: &Server{clientDBs: dbs}}
	res := resource.NewSchemaless(attribute.String("session", "shared"))
	const workers = 8
	var wg sync.WaitGroup
	errs := make(chan error, workers)
	for worker := range workers {
		wg.Go(func() {
			errs <- ps.Spans("client").ExportSpans(context.Background(), []sdktrace.ReadOnlySpan{
				resourceBatchSpan(2*worker+1, res), resourceBatchSpan(2*worker+2, res),
			})
		})
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		require.NoError(t, err)
	}
	db, err := dbs.Open(t.Context(), "client")
	require.NoError(t, err)
	defer db.Close()
	rows, err := db.SelectSpansSince(t.Context(), clientdb.SelectSpansSinceParams{Limit: 100})
	require.NoError(t, err)
	require.Len(t, rows, 2*workers)
	want, err := protojson.Marshal(telemetry.ResourcePtrToPB(res))
	require.NoError(t, err)
	for _, row := range rows {
		require.JSONEq(t, string(want), string(row.Resource))
	}
}

func BenchmarkSpanResourceBatch(b *testing.B) {
	for _, count := range []int{1, 128} {
		for _, distinct := range []bool{false, true} {
			b.Run(fmt.Sprintf("spans=%d/distinct=%t", count, distinct), func(b *testing.B) {
				dbs := clientdb.NewDBs(b.TempDir())
				b.Cleanup(func() { require.NoError(b, dbs.Close()) })
				ps := &PubSub{srv: &Server{clientDBs: dbs}}
				db, err := dbs.Open(b.Context(), "client")
				require.NoError(b, err)
				b.Cleanup(func() { require.NoError(b, db.Close()) })
				res := resource.NewSchemaless(attribute.String("service.name", "engine"), attribute.String("session", "shared"))
				spans := make([]sdktrace.ReadOnlySpan, count)
				for i := range spans {
					if distinct {
						res = resource.NewSchemaless(attribute.String("session", fmt.Sprint(i)))
					}
					spans[i] = resourceBatchSpan(i+1, res)
				}
				exporter := ps.Spans("client")
				b.ReportAllocs()
				for b.Loop() {
					if err := exporter.ExportSpans(b.Context(), spans); err != nil {
						b.Fatal(err)
					}
				}
			})
		}
	}
}
