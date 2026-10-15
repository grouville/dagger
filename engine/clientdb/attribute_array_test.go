package clientdb

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	otlpcommonv1 "go.opentelemetry.io/proto/otlp/common/v1"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func legacyUnmarshalProtoJSONs[T proto.Message](pb []byte, base T, out *[]T) error {
	var msgs []json.RawMessage
	if err := json.Unmarshal(pb, &msgs); err != nil {
		return err
	}
	protos := make([]T, len(msgs))
	for i, msg := range msgs {
		pl := proto.Clone(base).(T)
		if err := protojson.Unmarshal(msg, pl); err != nil {
			return err
		}
		protos[i] = pl
	}
	*out = protos
	return nil
}

func FuzzUnmarshalAttributeArray(f *testing.F) {
	encoded, err := MarshalProtoJSONs(sampleSpanAttrs())
	require.NoError(f, err)
	cases := []string{
		string(encoded), "[]", "null", " \n []\t", "[ \n ]", " \nnull\t", "[{}, {}]",
		"\v[]", "\fnull", "\u00a0[]\u00a0", "null\u2028",
		`[{"key":"a","value":{"intValue":"9223372036854775807"}},{"key":"b","value":{"doubleValue":"NaN"}}]`,
		"", "{}", `"[]"`, "[null]", "[{},]", "[{}] []",
		`[{"unknown":1}]`, `[{"key":"k","key":"duplicate"}]`,
		`[{"key":"k","value":{"intValue":"bad"}}]`,
		// Wrapping raw bytes must not accept an injected sibling field.
		`[],"values":[]`, `null,"values":[{}]`, `[],"unknown":[]`,
	}
	for _, data := range cases {
		f.Add([]byte(data))
	}
	f.Add([]byte(`[{"key":"deep","value":` + strings.Repeat(`{"arrayValue":{"values":[`, 3500) + `{"stringValue":"end"}` + strings.Repeat(`]}}`, 3500) + `}]`))
	f.Fuzz(func(t *testing.T, data []byte) {
		base := strAttr("base", "unchanged")
		sentinel := strAttr("output", "unchanged on error")
		before, after := []*otlpcommonv1.KeyValue{sentinel}, []*otlpcommonv1.KeyValue{sentinel}
		oldErr := legacyUnmarshalProtoJSONs(data, base, &before)
		newErr := UnmarshalProtoJSONs(data, base, &after)
		require.Equal(t, oldErr == nil, newErr == nil, "old: %v; new: %v", oldErr, newErr)
		require.Len(t, after, len(before))
		for i := range before {
			require.True(t, proto.Equal(before[i], after[i]), "attribute %d", i)
		}
		require.NotNil(t, after)
		if newErr != nil {
			require.Same(t, sentinel, after[0])
		}
		require.True(t, proto.Equal(strAttr("base", "unchanged"), base))
	})
}

func BenchmarkAttributeArrayDecode(b *testing.B) {
	for _, size := range []int{0, 4, 32, 1024} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			attrs := make([]*otlpcommonv1.KeyValue, size)
			for i := range attrs {
				attrs[i] = strAttr(fmt.Sprintf("key-%d", i), strings.Repeat("test", 8))
			}
			data, err := MarshalProtoJSONs(attrs)
			if err != nil {
				b.Fatal(err)
			}
			for _, variant := range []string{"legacy", "current"} {
				b.Run(variant, func(b *testing.B) {
					b.ReportAllocs()
					for b.Loop() {
						var out []*otlpcommonv1.KeyValue
						var err error
						if variant == "legacy" {
							err = legacyUnmarshalProtoJSONs(data, &otlpcommonv1.KeyValue{}, &out)
						} else {
							err = UnmarshalProtoJSONs(data, &otlpcommonv1.KeyValue{}, &out)
						}
						if err != nil {
							b.Fatal(err)
						}
					}
				})
			}
		})
	}
}
