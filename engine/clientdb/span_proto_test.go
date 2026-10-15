package clientdb

import (
	"database/sql"
	"fmt"
	"slices"
	"strings"
	"testing"

	telemetry "github.com/dagger/otel-go"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

func canonicalSpanGroups(groups []*tracepb.ResourceSpans) [][]byte {
	encoded := make([][]byte, len(groups))
	for i, group := range groups {
		encoded[i], _ = proto.MarshalOptions{Deterministic: true}.Marshal(group)
	}
	slices.SortFunc(encoded, func(a, b []byte) int { return slices.Compare(a, b) })
	return encoded
}

func spanConversionOutcome(convert func() []*tracepb.ResourceSpans) (groups [][]byte, panicValue any) {
	defer func() { panicValue = recover() }()
	return canonicalSpanGroups(convert()), nil
}

func TestStoredSpansToPBMatchesSDK(t *testing.T) {
	attributes := []string{
		`[]`, `null`,
		`[{"key":"k","value":{"stringValue":"hello\n世界"}}]`,
		`[{"key":"k","value":{"boolValue":false}}]`,
		`[{"key":"k","value":{"intValue":"-9223372036854775808"}}]`,
		`[{"key":"k","value":{"doubleValue":"NaN"}}]`,
		`[{"key":"k","value":{"doubleValue":-0.0}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"stringValue":"a"},{"stringValue":"b"}]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"boolValue":false},{"boolValue":true}]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"intValue":"1"},{"intValue":"2"}]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"doubleValue":1},{"doubleValue":"Infinity"}]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"boolValue":true},{"stringValue":"mixed"}]}}}]`,
		`[{"key":"k","value":{"arrayValue":{"values":[{"arrayValue":{"values":[]}}]}}}]`,
		`[{"key":"k","value":{"bytesValue":"AQID"}}]`,
		`[{"key":"k","value":{"kvlistValue":{"values":[]}}}]`,
		`[{"key":"k"}]`, `[null]`, `[{"key":"k","value":{}}]`,
		`[{"key":"duplicate","value":{"intValue":"1"}},{"key":"duplicate","value":{"intValue":"2"}}]`,
		`not json`, `[{"unknown":true}]`, `[{"key":"k","value":{"stringValue":"first","intValue":"2"}}]`,
	}
	for i, attrs := range attributes {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			rows := batchFixture(7)
			for i := range rows {
				rows[i].Attributes = []byte(attrs)
				rows[i].Kind = []string{"internal", "server", "client", "producer", "consumer", "unknown", ""}[i]
				rows[i].StatusCode = int64(i)
				rows[i].StatusMessage = "status"
				rows[i].Flags = 255
				rows[i].DroppedAttributesCount = int64(i)
				rows[i].DroppedLinksCount = int64(i + 1)
				rows[i].DroppedEventsCount = int64(i + 2)
			}
			rows[0].EndTime.Valid = false
			rows[1].ParentSpanID = sql.NullString{String: rows[0].SpanID, Valid: true}
			rows[1].TraceState = "one=first,two=second"
			rows[2].TraceID, rows[2].SpanID, rows[2].TraceState = "bad", "bad", "invalid"
			rows[3].StartTime, rows[3].EndTime.Int64 = -500, -100
			rows[4].Links = []byte(`[{"traceId":"AQIDBAUGBwgJCgsMDQ4PEA==","spanId":"AQIDBAUGBwg=","flags":768,"attributes":[{"key":"l","value":{"intValue":"3"}}]}]`)
			rows[5].Events = []byte(`[{"timeUnixNano":"5","name":"event","attributes":[{"key":"e","value":{"boolValue":true}}],"droppedAttributesCount":2}]`)
			rows[6].Links, rows[6].Events = []byte(`bad`), []byte(`bad`)
			want, oldPanic := spanConversionOutcome(func() []*tracepb.ResourceSpans {
				return telemetry.SpansToPB(ReadOnlySpans(rows))
			})
			got, newPanic := spanConversionOutcome(func() []*tracepb.ResourceSpans { return SpansToPB(rows) })
			require.Equal(t, fmt.Sprint(oldPanic), fmt.Sprint(newPanic), "preserve existing malformed-input behavior")
			require.Equal(t, want, got)
		})
	}
}

func TestStoredSpansToPBGroupingAndIsolation(t *testing.T) {
	rows := batchFixture(5)
	rows[1].Resource = []byte(`{"attributes":[{"value":{"stringValue":"engine"},"key":"service.name"}]}`)
	rows[2].Resource = []byte(`{"attributes":[{"key":"service.name","value":{"stringValue":"other"}}]}`)
	rows[3].InstrumentationScope = []byte(`{"name":"other"}`)
	rows[4].Resource, rows[4].InstrumentationScope = []byte(`invalid`), []byte(`invalid`)
	rows[2].ResourceSchemaURL = "ignored-by-the-existing-reader"
	want := canonicalSpanGroups(telemetry.SpansToPB(ReadOnlySpans(rows)))
	got := SpansToPB(rows)
	require.Equal(t, want, canonicalSpanGroups(got))
	got[0].ScopeSpans[0].Spans[0].Attributes[0].Key = "mutated output"
	require.Equal(t, want, canonicalSpanGroups(SpansToPB(rows)), "later batches must not inherit mutated output")
	require.Nil(t, SpansToPB(nil))
}

func BenchmarkStoredSpansToPB(b *testing.B) {
	for _, count := range []int{1, 16} {
		for _, linked := range []bool{false, true} {
			rows := batchFixture(512)
			attrs := make([]attribute.KeyValue, count)
			for i := range attrs {
				key := fmt.Sprintf("attribute-%d", i)
				switch i % 4 {
				case 0:
					attrs[i] = attribute.String(key, strings.Repeat("x", 64))
				case 1:
					attrs[i] = attribute.Int64(key, int64(i))
				case 2:
					attrs[i] = attribute.Bool(key, true)
				case 3:
					attrs[i] = attribute.StringSlice(key, []string{"dependency-a", "dependency-b"})
				}
			}
			encoded, err := MarshalProtoJSONs(telemetry.KeyValues(attrs))
			if err != nil {
				b.Fatal(err)
			}
			for i := range rows {
				rows[i].Attributes = encoded
				if linked {
					rows[i].Links = []byte(`[{"traceId":"AQIDBAUGBwgJCgsMDQ4PEA==","spanId":"AQIDBAUGBwg=","attributes":[{"key":"reason","value":{"stringValue":"wait"}}]}]`)
				}
			}
			for _, direct := range []bool{false, true} {
				b.Run(fmt.Sprintf("attrs-%d/linked-%t/direct-%t", count, linked, direct), func(b *testing.B) {
					b.ReportAllocs()
					for b.Loop() {
						if direct {
							_ = SpansToPB(rows)
						} else {
							_ = telemetry.SpansToPB(ReadOnlySpans(rows))
						}
					}
				})
			}
		}
	}
}
