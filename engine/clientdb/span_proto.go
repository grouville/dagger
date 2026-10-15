package clientdb

import (
	"bytes"

	telemetry "github.com/dagger/otel-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/sdk/instrumentation"
	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

// SpansToPB forwards stored spans using the same resource and scope grouping as
// the SDK converter, without recreating SDK attribute values for ordinary rows.
func SpansToPB(rows []Span) []*tracepb.ResourceSpans {
	if len(rows) == 0 {
		return nil
	}
	type scopeKey struct {
		resource attribute.Distinct
		scope    instrumentation.Scope
	}
	resources := make(map[attribute.Distinct]*tracepb.ResourceSpans)
	scopes := make(map[scopeKey]*tracepb.ScopeSpans)
	result := make([]*tracepb.ResourceSpans, 0)
	for _, span := range ReadOnlySpans(rows) {
		ro := span.(*readOnlySpan)
		resource := ro.Resource()
		resourceKey := resource.Equivalent()
		group, ok := resources[resourceKey]
		if !ok {
			group = &tracepb.ResourceSpans{
				Resource:  telemetry.ResourcePtrToPB(resource),
				SchemaUrl: resource.SchemaURL(),
			}
			resources[resourceKey] = group
			result = append(result, group)
		}
		scope := ro.InstrumentationScope()
		key := scopeKey{resource: resourceKey, scope: scope}
		batch, ok := scopes[key]
		if !ok {
			batch = &tracepb.ScopeSpans{
				Scope:     telemetry.InstrumentationScopeToPB(scope),
				SchemaUrl: scope.SchemaURL,
			}
			scopes[key] = batch
			group.ScopeSpans = append(group.ScopeSpans, batch)
		}
		batch.Spans = append(batch.Spans, storedSpanToPB(ro))
	}
	return result
}

func storedSpanToPB(ro *readOnlySpan) *tracepb.Span {
	var attrs []*commonpb.KeyValue
	err := UnmarshalProtoJSONs(ro.DB.Attributes, &commonpb.KeyValue{}, &attrs)
	if err != nil {
		// Preserve the existing reader's warnings and malformed-input behavior.
		attrs = telemetry.KeyValues(ro.Attributes())
	} else if !sdkAttributesUnchanged(attrs) {
		attrs = telemetry.KeyValues(telemetry.AttributesFromProto(attrs))
	}
	if len(attrs) == 0 {
		attrs = nil
	}
	sc, parent := ro.SpanContext(), ro.Parent()
	tid, sid := sc.TraceID(), sc.SpanID()
	status := ro.Status()
	code := tracepb.Status_STATUS_CODE_UNSET
	switch status.Code {
	case codes.Ok:
		code = tracepb.Status_STATUS_CODE_OK
	case codes.Error:
		code = tracepb.Status_STATUS_CODE_ERROR
	}
	kind := tracepb.Span_SpanKind(ro.SpanKind())
	span := &tracepb.Span{
		TraceId:                tid[:],
		SpanId:                 sid[:],
		TraceState:             sc.TraceState().String(),
		Name:                   ro.DB.Name,
		Kind:                   kind,
		StartTimeUnixNano:      uint64(ro.StartTime().UnixNano()),
		EndTimeUnixNano:        uint64(ro.EndTime().UnixNano()),
		Attributes:             attrs,
		Status:                 &tracepb.Status{Code: code, Message: status.Description},
		DroppedAttributesCount: uint32(ro.DB.DroppedAttributesCount),
		DroppedLinksCount:      uint32(ro.DB.DroppedLinksCount),
		DroppedEventsCount:     uint32(ro.DB.DroppedEventsCount),
		// The SDK converter derives flags from Parent(), which stores no remote bit.
		Flags: uint32(tracepb.SpanFlags_SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK),
	}
	// Nonempty links and events retain their existing SDK normalization.
	if !emptyProtoArray(ro.DB.Links) {
		span.Links = telemetry.SpanLinksToPB(ro.Links())
	}
	if !emptyProtoArray(ro.DB.Events) {
		span.Events = telemetry.SpanEventsToPB(ro.Events())
	}
	if id := parent.SpanID(); id.IsValid() {
		span.ParentSpanId = id[:]
	}
	return span
}

func emptyProtoArray(data []byte) bool {
	// Only JSON whitespace is allowed; malformed data must reach the old reader.
	data = bytes.Trim(data, " \r\n\t")
	return bytes.Equal(data, []byte("[]")) || bytes.Equal(data, []byte("null"))
}

// sdkAttributesUnchanged recognizes values the SDK round trip preserves. In
// particular, mixed and nested arrays must use its existing string conversion.
func sdkAttributesUnchanged(attrs []*commonpb.KeyValue) bool {
	for _, attr := range attrs {
		if attr == nil || attr.Value == nil {
			return false
		}
		if scalarValueKind(attr.Value) != 0 {
			continue
		}
		array, ok := attr.Value.Value.(*commonpb.AnyValue_ArrayValue)
		if !ok || array.ArrayValue == nil {
			return false
		}
		kind := 0
		for _, value := range array.ArrayValue.Values {
			current := scalarValueKind(value)
			if current == 0 || (kind != 0 && current != kind) {
				return false
			}
			kind = current
		}
	}
	return true
}

func scalarValueKind(value *commonpb.AnyValue) int {
	if value == nil {
		return 0
	}
	switch value.Value.(type) {
	case *commonpb.AnyValue_StringValue:
		return 1
	case *commonpb.AnyValue_BoolValue:
		return 2
	case *commonpb.AnyValue_IntValue:
		return 3
	case *commonpb.AnyValue_DoubleValue:
		return 4
	default:
		return 0
	}
}
