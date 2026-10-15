package clientdb

import (
	"database/sql"
	"fmt"
	"testing"

	telemetry "github.com/dagger/otel-go"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/protobuf/proto"
)

func batchFixture(n int) []Span {
	spans := make([]Span, n)
	for i := range spans {
		spans[i] = Span{
			TraceID: "0102030405060708090a0b0c0d0e0f10", SpanID: fmt.Sprintf("%016x", i+1),
			Name: fmt.Sprintf("call-%d", i), Kind: "internal", StartTime: 123,
			EndTime:    sql.NullInt64{Int64: 456, Valid: true},
			Attributes: []byte(`[{"key":"argument","value":{"stringValue":"hello"}}]`),
			Events:     []byte(`[]`), Links: []byte(`[]`),
			Resource:             []byte(`{"attributes":[{"key":"service.name","value":{"stringValue":"engine"}}]}`),
			InstrumentationScope: []byte(`{"name":"dagger","version":"1"}`),
		}
	}
	return spans
}

func TestReadOnlySpansPreservesBatch(t *testing.T) {
	rows := batchFixture(3)
	rows[2].Resource = []byte(`{"attributes":[{"key":"service.name","value":{"stringValue":"compiler"}}]}`)
	rows[2].InstrumentationScope = []byte(`{"name":"rustc","version":"2"}`)
	legacy := make([]sdktrace.ReadOnlySpan, len(rows))
	for i := range rows {
		legacy[i] = rows[i].ReadOnly()
	}
	got, want := telemetry.SpansToPB(ReadOnlySpans(rows)), telemetry.SpansToPB(legacy)
	byName := map[string]proto.Message{}
	for _, resource := range want {
		byName[resource.Resource.Attributes[0].Value.GetStringValue()] = resource
	}
	require.Len(t, got, len(want))
	for _, resource := range got {
		require.True(t, proto.Equal(resource, byName[resource.Resource.Attributes[0].Value.GetStringValue()]))
	}
	// A new batch must not inherit metadata from the earlier one.
	rows[0].Resource = rows[2].Resource
	next := ReadOnlySpans(rows[:1])
	require.Equal(t, "compiler", next[0].Resource().Attributes()[0].Value.AsString())
}

func BenchmarkReadOnlySpanBatch(b *testing.B) {
	rows := batchFixture(512)
	for _, batch := range []bool{false, true} {
		b.Run(fmt.Sprint(batch), func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				var spans []sdktrace.ReadOnlySpan
				if batch {
					spans = ReadOnlySpans(rows)
				} else {
					spans = make([]sdktrace.ReadOnlySpan, 0, len(rows))
					for i := range rows {
						spans = append(spans, rows[i].ReadOnly())
					}
				}
				_ = telemetry.SpansToPB(spans)
			}
		})
	}
}
