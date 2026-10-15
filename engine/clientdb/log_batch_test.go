package clientdb

import (
	"database/sql"
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
	otlpcommonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	"google.golang.org/protobuf/proto"
)

func logBatchFixture(n int) []Log {
	logs := make([]Log, n)
	for i := range logs {
		body, err := proto.Marshal(&otlpcommonv1.AnyValue{
			Value: &otlpcommonv1.AnyValue_StringValue{StringValue: fmt.Sprint(i)},
		})
		if err != nil {
			panic(err)
		}
		logs[i] = Log{
			TraceID:              sql.NullString{String: "0102030405060708090a0b0c0d0e0f10", Valid: true},
			SpanID:               sql.NullString{String: fmt.Sprintf("%016x", i+1), Valid: true},
			Timestamp:            int64(i + 123),
			SeverityNumber:       9,
			SeverityText:         "INFO",
			Body:                 body,
			Attributes:           []byte(`[{"key":"stdio.stream","value":{"stringValue":"stdout"}}]`),
			Resource:             []byte(`{"attributes":[{"key":"service.name","value":{"stringValue":"engine"}}]}`),
			ResourceSchemaURL:    "https://example.com/resource/v1",
			InstrumentationScope: []byte(`{"name":"dagger","version":"1"}`),
		}
	}
	return logs
}

func TestLogsToPBPreservesBatchMetadata(t *testing.T) {
	rows := logBatchFixture(6)
	rows[1].ResourceSchemaURL = "https://example.com/resource/v2"
	rows[2].InstrumentationScope = []byte(`{"name":"rustc","version":"2"}`)
	rows[3].Resource = []byte(`{"attributes":[{"key":"service.name","value":{"stringValue":"compiler"}}]}`)
	// Distinct JSON for an equivalent resource still belongs to the same group.
	rows[4].Resource = []byte(`{ "attributes": [{ "key": "service.name", "value": { "stringValue": "engine" } }] }`)
	invalidResource, invalidScope, invalidBody := rows[0], rows[0], rows[0]
	invalidResource.Resource = []byte(`{`)
	invalidScope.InstrumentationScope = []byte(`{`)
	invalidBody.Body = []byte{0xff}
	input := append([]Log{invalidResource, invalidScope, invalidBody}, rows...)
	got := LogsToPB(input)
	require.Len(t, got, 2)
	groups := map[string]map[string][]string{}
	for _, res := range got {
		service := res.Resource.Attributes[0].Value.GetStringValue()
		groups[service] = map[string][]string{}
		require.Equal(t, "https://example.com/resource/v1", res.SchemaUrl)
		for _, scope := range res.ScopeLogs {
			require.Empty(t, scope.SchemaUrl)
			for _, record := range scope.LogRecords {
				body := record.Body.GetStringValue()
				groups[service][scope.Scope.Name] = append(groups[service][scope.Scope.Name], body)
				require.Equal(t, "stdout", record.Attributes[0].Value.GetStringValue())
				require.Equal(t, "INFO", record.SeverityText)
			}
		}
	}
	require.Equal(t, map[string]map[string][]string{
		"engine":   {"dagger": {"0", "1", "4", "5"}, "rustc": {"2"}},
		"compiler": {"dagger": {"3"}},
	}, groups)
	// Exported groups own their mutable protobuf metadata independently.
	got[0].ScopeLogs[0].Scope.Name = "changed"
	require.NotEqual(t, "changed", got[1].ScopeLogs[0].Scope.Name)
	// A subsequent batch gets its own decoded metadata and output objects.
	rows[0].Resource = rows[3].Resource
	next := LogsToPB(rows[:1])
	require.Equal(t, "compiler", next[0].Resource.Attributes[0].Value.GetStringValue())
	require.Len(t, got, 2)
}

func BenchmarkLogMetadataBatch(b *testing.B) {
	for _, size := range []int{1, 512} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			rows := logBatchFixture(size)
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				_ = LogsToPB(rows)
			}
		})
	}
}
