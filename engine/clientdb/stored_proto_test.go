package clientdb

import (
	"bytes"
	"database/sql"
	"encoding/base64"
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/dagger/dagger/dagql/call/callpbv1"
	telemetry "github.com/dagger/otel-go"
	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	metricpb "go.opentelemetry.io/proto/otlp/metrics/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func storageNative(t *testing.T, kind byte, message proto.Message) []byte {
	t.Helper()
	data, err := marshalNativeProto(kind, message)
	require.NoError(t, err)
	return data
}

func TestStoredProtoForwardingMatchesJSON(t *testing.T) {
	// A missing AnyValue is malformed for the existing SDK converter. Keep
	// that case in the decoder tests; this fixture represents exported data.
	var attrs []*commonpb.KeyValue
	for _, attr := range sampleSpanAttrs() {
		if attr.Value != nil {
			attrs = append(attrs, attr)
		}
	}
	attrs = append(attrs, &commonpb.KeyValue{Key: "special", Value: &commonpb.AnyValue{
		Value: &commonpb.AnyValue_DoubleValue{DoubleValue: math.NaN()},
	}})
	events := []*tracepb.Span_Event{{Name: "event", TimeUnixNano: 123, Attributes: attrs, DroppedAttributesCount: 3}}
	links := []*tracepb.Span_Link{{TraceId: bytes.Repeat([]byte{1}, 16), SpanId: bytes.Repeat([]byte{2}, 8), Attributes: attrs, DroppedAttributesCount: 2, Flags: 0x101}}
	resource := &resourcepb.Resource{Attributes: []*commonpb.KeyValue{strAttr("service.name", "test")}, DroppedAttributesCount: 4}
	scope := &commonpb.InstrumentationScope{Name: "scope", Version: "version", Attributes: []*commonpb.KeyValue{strAttr("scope", "attribute")}}
	legacy := Span{TraceID: "0102030405060708090a0b0c0d0e0f10", SpanID: "1112131415161718", ParentSpanID: validString("2122232425262728"), Name: "span", Kind: "client", StartTime: 123, EndTime: sql.NullInt64{Int64: 456, Valid: true}, StatusCode: 2, StatusMessage: "status", Flags: 1, DroppedAttributesCount: 7, DroppedEventsCount: 8, DroppedLinksCount: 9, ResourceSchemaURL: "schema"}
	var err error
	legacy.Attributes, err = MarshalProtoJSONs(attrs)
	require.NoError(t, err)
	legacy.Events, err = MarshalProtoJSONs(events)
	require.NoError(t, err)
	legacy.Links, err = MarshalProtoJSONs(links)
	require.NoError(t, err)
	legacy.Resource, err = protojson.Marshal(resource)
	require.NoError(t, err)
	legacy.InstrumentationScope, err = protojson.Marshal(scope)
	require.NoError(t, err)
	native := legacy
	native.Attributes = storageNative(t, storedAttributes, &commonpb.KeyValueList{Values: attrs})
	native.Events = storageNative(t, storedEvents, &tracepb.Span{Events: events})
	native.Links = storageNative(t, storedLinks, &tracepb.Span{Links: links})
	native.Resource = storageNative(t, storedResource, resource)
	native.InstrumentationScope = storageNative(t, storedScope, scope)
	a := telemetry.SpansToPB([]sdktrace.ReadOnlySpan{legacy.ReadOnly()})
	b := telemetry.SpansToPB([]sdktrace.ReadOnlySpan{native.ReadOnly()})
	require.Len(t, a, 1)
	require.Len(t, b, 1)
	require.True(t, proto.Equal(a[0], b[0]), "complete exported span differs")

	body, err := proto.Marshal(&commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: "body"}})
	require.NoError(t, err)
	log := Log{TraceID: validString(legacy.TraceID), SpanID: validString(legacy.SpanID), Timestamp: 123, SeverityNumber: 9, SeverityText: "INFO", Body: body, Attributes: legacy.Attributes, Resource: legacy.Resource, InstrumentationScope: legacy.InstrumentationScope, ResourceSchemaURL: "schema"}
	nativeLog := log
	nativeLog.Attributes, nativeLog.Resource, nativeLog.InstrumentationScope = native.Attributes, native.Resource, native.InstrumentationScope
	jsonLogs, nativeLogs := LogsToPB([]Log{log}), LogsToPB([]Log{nativeLog})
	require.Len(t, jsonLogs, 1)
	require.Len(t, nativeLogs, 1)
	require.True(t, proto.Equal(jsonLogs[0], nativeLogs[0]), "complete exported log differs")
	metrics := &metricpb.ResourceMetrics{Resource: resource, SchemaUrl: "schema", ScopeMetrics: []*metricpb.ScopeMetrics{{Scope: scope, Metrics: []*metricpb.Metric{{Name: "metric", Unit: "s"}}}}}
	jsonMetrics, err := protojson.Marshal(metrics)
	require.NoError(t, err)
	jsonMetricRows, nativeMetricRows := MetricsToPB([]Metric{{Data: jsonMetrics}}), MetricsToPB([]Metric{{Data: storageNative(t, storedMetrics, metrics)}})
	require.Len(t, jsonMetricRows, 1)
	require.Len(t, nativeMetricRows, 1)
	require.True(t, proto.Equal(jsonMetricRows[0], nativeMetricRows[0]), "complete exported metric differs")
}

func TestStoredProtoRejectsCorruptionAndWrongKind(t *testing.T) {
	valid := storageNative(t, storedAttributes, &commonpb.KeyValueList{Values: sampleSpanAttrs()})
	unknownVersion := bytes.Clone(valid)
	unknownVersion[3]++
	unknownKind := bytes.Clone(valid)
	unknownKind[4] = 99
	for _, data := range [][]byte{{0}, []byte("\x00bad"), unknownVersion, unknownKind, valid[:len(valid)-1]} {
		var out []*commonpb.KeyValue
		require.Error(t, UnmarshalStoredProtos(data, &commonpb.KeyValue{}, &out))
		require.Nil(t, out)
	}
	var links []*tracepb.Span_Link
	require.Error(t, UnmarshalStoredProtos(valid, &tracepb.Span_Link{}, &links))
	_, err := marshalNativeProto(storedAttributes, &commonpb.KeyValueList{Values: []*commonpb.KeyValue{strAttr("key", string([]byte{0xff}))}})
	require.Error(t, err)
	// A malformed recovery must not publish a format upgrade.
	file := filepath.Join(t.TempDir(), "bad.metrics.log")
	require.NoError(t, os.WriteFile(file, []byte{1, 1, 0xff}, 0o600))
	_, err = openSpillFile(t.Context(), file, metricCodec, nil)
	require.Error(t, err)
	data, err := os.ReadFile(file)
	require.NoError(t, err)
	require.Equal(t, byte(1), data[0])
}

func TestStoredProtoEmptyNilAndBufferOwnership(t *testing.T) {
	for _, values := range [][]*commonpb.KeyValue{nil, {}, {nil, strAttr("k", "v")}} {
		data := storageNative(t, storedAttributes, &commonpb.KeyValueList{Values: values})
		var out []*commonpb.KeyValue
		require.NoError(t, UnmarshalStoredProtos(data, &commonpb.KeyValue{}, &out))
		require.NotNil(t, out)
		require.Len(t, out, len(values))
		if len(values) > 0 {
			require.NotNil(t, out[0])
			require.Equal(t, "v", out[1].GetValue().GetStringValue())
			clear(data)
			require.Equal(t, "v", out[1].GetValue().GetStringValue())
		}
	}
	empty := storageNative(t, storedLinks, &tracepb.Span{})
	require.Empty(t, causalLinkTargets(Span{SpanID: "s", Links: empty}))
}

func TestStoredProtoMixedHistoryReopensAndRebuildsIndexes(t *testing.T) {
	root := t.TempDir()
	store, err := openStore(t.Context(), root, "mixed", 256)
	require.NoError(t, err)
	frame := &callpbv1.Call{Digest: "xxh3:abc", Field: "directory"}
	frameBytes, err := proto.Marshal(frame)
	require.NoError(t, err)
	attrs := []*commonpb.KeyValue{strAttr(telemetry.DagDigestAttr, frame.Digest), strAttr(telemetry.DagCallAttr, base64.StdEncoding.EncodeToString(frameBytes)), strAttr(telemetry.CheckNameAttr, "go:test"), strAttr("test.case.name", "a test")}
	legacy, err := MarshalProtoJSONs(attrs)
	require.NoError(t, err)
	_, err = store.AppendSpans([]Span{{TraceID: "trace", SpanID: "old", Attributes: legacy}})
	require.NoError(t, err)
	require.NoError(t, store.Close())
	// The row framing is identical; this creates a real legacy-v1 fixture.
	for _, stream := range []string{"spans", "logs", "metrics"} {
		path := filepath.Join(root, "mixed."+stream+".log")
		file, err := os.OpenFile(path, os.O_WRONLY, 0)
		require.NoError(t, err)
		_, err = file.WriteAt([]byte{1}, 0)
		require.NoError(t, err)
		require.NoError(t, file.Close())
	}
	var dump bytes.Buffer
	require.NoError(t, Dump(t.Context(), root, "mixed", DumpAll, &dump))
	before, err := os.ReadFile(filepath.Join(root, "mixed.spans.log"))
	require.NoError(t, err)
	require.Equal(t, byte(1), before[0], "dump must remain read-only")
	store, err = openStore(t.Context(), root, "mixed", 256)
	require.NoError(t, err)
	native := storageNative(t, storedAttributes, &commonpb.KeyValueList{Values: attrs})
	_, err = store.AppendSpans([]Span{{TraceID: "trace", SpanID: "new", Attributes: native}})
	require.NoError(t, err)
	log := callPayloadLog(t, &callpbv1.Call{Digest: "xxh3:log", Field: "file"})
	var logAttrs []*commonpb.KeyValue
	require.NoError(t, UnmarshalStoredProtos(log.Attributes, &commonpb.KeyValue{}, &logAttrs))
	log.Attributes = storageNative(t, storedAttributes, &commonpb.KeyValueList{Values: logAttrs})
	_, err = store.AppendLogs([]Log{log})
	require.NoError(t, err)
	require.NoError(t, store.Close())
	store, err = openStore(t.Context(), root, "mixed", 256)
	require.NoError(t, err)
	defer store.Close()
	checks, tests := store.CheckTestSpanIDs()
	require.ElementsMatch(t, []string{"old", "new"}, keysOf(checks))
	require.ElementsMatch(t, []string{"old", "new"}, keysOf(tests))
	require.ElementsMatch(t, []string{"xxh3:abc", "xxh3:log"}, keysOf(store.CallDigests()))
	frames, err := store.SelectCallFrames(t.Context(), store.CallDigests())
	require.NoError(t, err)
	require.Len(t, frames, 2)
	for _, frame := range frames {
		switch frame.Digest {
		case "xxh3:abc":
			require.NotNil(t, frame.Span)
			require.Equal(t, "new", frame.Span.SpanID)
			require.EqualValues(t, 2, frame.Span.ID)
		case "xxh3:log":
			require.NotNil(t, frame.Log)
			decoded, err := CallPayloadBody(*frame.Log)
			require.NoError(t, err)
			require.Equal(t, "file", decoded.GetField())
		default:
			t.Fatalf("unexpected call digest %s", frame.Digest)
		}
	}
	rows, err := store.SelectSpansSince(t.Context(), SelectSpansSinceParams{Limit: 10})
	require.NoError(t, err)
	require.Len(t, rows, 2)
	require.Equal(t, legacy, rows[0].Attributes)
	require.Equal(t, native, rows[1].Attributes)
	for _, stream := range []string{"spans", "logs", "metrics"} {
		data, err := os.ReadFile(filepath.Join(root, "mixed."+stream+".log"))
		require.NoError(t, err)
		require.Equal(t, byte(2), data[0], "old engines must refuse the upgraded store")
	}
	dump.Reset()
	require.NoError(t, store.Close())
	require.NoError(t, Dump(t.Context(), root, "mixed", DumpAll, &dump))
}

func BenchmarkStoredProtoAttributes(b *testing.B) {
	attrs := sampleSpanAttrs()
	for _, tc := range []struct {
		name   string
		encode func([]*commonpb.KeyValue) ([]byte, error)
	}{
		{"JSON", MarshalProtoJSONs[*commonpb.KeyValue]},
		{"native", MarshalStoredProtos[*commonpb.KeyValue]},
	} {
		b.Run(tc.name, func(b *testing.B) {
			data, err := tc.encode(attrs)
			if err != nil {
				b.Fatal(err)
			}
			b.Run("encode-and-index", func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					encoded, err := tc.encode(attrs)
					if err != nil {
						b.Fatal(err)
					}
					if _, ok := spanCallDigest(Span{Attributes: encoded}); !ok {
						b.Fatal("encoded call frame was not indexed")
					}
				}
			})
			b.Run("decode", func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					var decoded []*commonpb.KeyValue
					if err := UnmarshalStoredProtos(data, &commonpb.KeyValue{}, &decoded); err != nil {
						b.Fatal(err)
					}
				}
			})
		})
	}
}
