package clientdb

import (
	"log/slog"

	telemetry "github.com/dagger/otel-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/sdk/instrumentation"
	"go.opentelemetry.io/otel/trace"
	otlpcommonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	otlplogsv1 "go.opentelemetry.io/proto/otlp/logs/v1"
	otlpresourcev1 "go.opentelemetry.io/proto/otlp/resource/v1"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func LogsToPB(dbLog []Log) []*otlplogsv1.ResourceLogs {
	if !BatchMetadataEnabled() { return legacyLogsToPB(dbLog) }
	if len(dbLog) == 0 {
		return nil
	}

	rsm := make(map[attribute.Distinct]*otlplogsv1.ResourceLogs)

	type key struct {
		r  attribute.Distinct
		is instrumentation.Scope
	}
	ssm := make(map[key]*otlplogsv1.ScopeLogs)
	type resourceJSONKey struct {
		schemaURL string
		json      string
	}
	type decodedResource struct {
		key attribute.Distinct
		pb  *otlpresourcev1.Resource
	}
	type decodedScope struct {
		scope instrumentation.Scope
		pb    *otlpcommonv1.InstrumentationScope
	}
	// These caches belong to this batch. Failed decodes remain per-record
	// errors, and the next batch cannot inherit stale metadata.
	resourceCache := make(map[resourceJSONKey]decodedResource)
	scopeCache := make(map[string]decodedScope)

	var resources int
	for _, sd := range dbLog {
		resourceKey := resourceJSONKey{schemaURL: sd.ResourceSchemaURL, json: string(sd.Resource)}
		res, ok := resourceCache[resourceKey]
		if !ok {
			pb := &otlpresourcev1.Resource{}
			if err := protojson.Unmarshal(sd.Resource, pb); err != nil {
				slog.Error("failed to unmarshal log resource", "error", err, "log", sd)
				continue
			}
			res = decodedResource{key: telemetry.ResourceFromPB(sd.ResourceSchemaURL, pb).Equivalent(), pb: pb}
			resourceCache[resourceKey] = res
		}
		scopeKey := string(sd.InstrumentationScope)
		decoded, ok := scopeCache[scopeKey]
		if !ok {
			pb := &otlpcommonv1.InstrumentationScope{}
			if err := protojson.Unmarshal(sd.InstrumentationScope, pb); err != nil {
				slog.Error("failed to unmarshal instrumentation scope", "error", err, "log", sd)
				continue
			}
			decoded = decodedScope{scope: telemetry.InstrumentationScopeFromPB(pb), pb: pb}
			scopeCache[scopeKey] = decoded
		}
		rKey := res.key
		k := key{
			r:  rKey,
			is: decoded.scope,
		}
		scopeLog, iOk := ssm[k]
		if !iOk {
			// Either the resource or instrumentation scope were unknown.
			scopeLog = &otlplogsv1.ScopeLogs{
				Scope:      proto.Clone(decoded.pb).(*otlpcommonv1.InstrumentationScope),
				LogRecords: []*otlplogsv1.LogRecord{},
				SchemaUrl:  decoded.scope.SchemaURL,
			}
		}
		var bodyPb otlpcommonv1.AnyValue
		if err := proto.Unmarshal(sd.Body, &bodyPb); err != nil {
			slog.Warn("failed to unmarshal log body", "error", err, "log", sd)
			continue
		}
		var attrs []*otlpcommonv1.KeyValue
		if err := UnmarshalProtoJSONs(sd.Attributes, &otlpcommonv1.KeyValue{}, &attrs); err != nil {
			slog.Warn("failed to unmarshal log attributes", "error", err)
			continue
		}
		if !sd.TraceID.Valid || !sd.SpanID.Valid {
			slog.Error("log record has invalid trace or span ID", "log", sd)
			continue
		}
		tid, err := trace.TraceIDFromHex(sd.TraceID.String)
		if err != nil {
			slog.Error("failed to unmarshal trace id", "error", err)
			continue
		}
		sid, err := trace.SpanIDFromHex(sd.SpanID.String)
		if err != nil {
			slog.Error("failed to unmarshal span id", "error", err)
			continue
		}
		scopeLog.LogRecords = append(scopeLog.LogRecords, &otlplogsv1.LogRecord{
			TimeUnixNano:   uint64(sd.Timestamp),
			SeverityNumber: otlplogsv1.SeverityNumber(sd.SeverityNumber),
			SeverityText:   sd.SeverityText,
			Body:           &bodyPb,
			Attributes:     attrs,
			TraceId:        tid[:],
			SpanId:         sid[:],
		})
		ssm[k] = scopeLog

		rs, rOk := rsm[rKey]
		if !rOk {
			resources++
			// The resource was unknown.
			rs = &otlplogsv1.ResourceLogs{
				Resource:  res.pb,
				ScopeLogs: []*otlplogsv1.ScopeLogs{scopeLog},
				SchemaUrl: sd.ResourceSchemaURL,
			}
			rsm[rKey] = rs
			continue
		}

		// The resource has been seen before. Check if the instrumentation
		// library lookup was unknown because if so we need to add it to the
		// ResourceSpans. Otherwise, the instrumentation library has already
		// been seen and the append we did above will be included it in the
		// ScopeSpans reference.
		if !iOk {
			rs.ScopeLogs = append(rs.ScopeLogs, scopeLog)
		}
	}

	// Transform the categorized map into a slice
	rss := make([]*otlplogsv1.ResourceLogs, 0, resources)
	for _, rs := range rsm {
		rss = append(rss, rs)
	}
	recordLogBatchMetadata(len(dbLog), len(resourceCache), len(scopeCache))
	return rss
}
