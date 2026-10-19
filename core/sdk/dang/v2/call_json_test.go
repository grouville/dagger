package dangv2

import (
	"bytes"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

func decodeCallJSONReference(data []byte, dest any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	return decoder.Decode(dest)
}

func compareCallJSON(t testing.TB, data []byte) {
	t.Helper()
	for _, object := range []bool{false, true} {
		var want, got any
		var wantErr, gotErr error
		if object {
			var a, b map[string]any
			wantErr, gotErr = decodeCallJSONReference(data, &a), decodeCallJSON(data, &b)
			want, got = a, b
		} else {
			wantErr, gotErr = decodeCallJSONReference(data, &want), decodeCallJSON(data, &got)
		}
		if (wantErr == nil) != (gotErr == nil) {
			t.Fatalf("object=%v input=%q: standard error=%v, buffer error=%v", object, data, wantErr, gotErr)
		}
		if wantErr != nil {
			if reflect.TypeOf(wantErr) != reflect.TypeOf(gotErr) || wantErr.Error() != gotErr.Error() {
				t.Fatalf("object=%v input=%q: standard %T %v, buffer %T %v", object, data, wantErr, wantErr, gotErr, gotErr)
			}
		} else if !reflect.DeepEqual(want, got) {
			t.Fatalf("object=%v input=%q: standard %#v, buffer %#v", object, data, want, got)
		}
	}
}

var callJSONCases = []string{
	`{}`, `null`, `[]`, `true`, `42`, `"text"`, "", " \n\t ",
	`{"big":9007199254740993,"negative":-9223372036854775809,"exp":1.234567890123456789e1000,"zero":-0}`,
	`{"duplicate":1,"duplicate":2,"nested":{"array":[null,true,false,1,"value"]}}`,
	`{"unicode":"é 🦀 \uD83E\uDD80 \uD800 \uDC00","escaped":"\u0000\n\t\\\""}`,
	"{\"invalid\":\"\xff\xfe\"}", `{"n":NaN}`, `{"n":01}`, `{"n":1e}`, `{"n":+1}`,
	`{"a":1,}`, `{"a":}`, `{"a":`, `{"a":1} {"second":2}`, `{"a":1} trailing`,
}

func TestDecodeCallJSONMatchesDecoder(t *testing.T) {
	for i, data := range callJSONCases {
		t.Run(fmt.Sprint(i), func(t *testing.T) { compareCallJSON(t, []byte(data)) })
	}
	compareCallJSON(t, []byte(strings.Repeat("[", 1024)+"null"+strings.Repeat("]", 1024)))
}

func TestDecodeCallJSONKeepsInputPrivate(t *testing.T) {
	data := []byte(`{"key":"private-value","number":9007199254740993}`)
	var got map[string]any
	if err := decodeCallJSON(data, &got); err != nil {
		t.Fatal(err)
	}
	for i := range data {
		data[i] = 'x'
	}
	if got["key"] != "private-value" || got["number"] != json.Number("9007199254740993") {
		t.Fatalf("decoded values alias input: %#v", got)
	}
}

func FuzzDecodeCallJSONMatchesDecoder(f *testing.F) {
	for _, data := range callJSONCases {
		f.Add([]byte(data))
	}
	f.Fuzz(func(t *testing.T, data []byte) {
		if len(data) > 128*1024 {
			t.Skip()
		}
		compareCallJSON(t, data)
	})
}

var callJSONBenchmarkSink map[string]any

func BenchmarkDecodeCallJSON(b *testing.B) {
	for _, paths := range []int{1, 64, 800} {
		values := make([]string, paths)
		for i := range values {
			values[i] = fmt.Sprintf("module/package/%04d", i)
		}
		data, err := json.Marshal(map[string]any{"paths": values, "name": "collection", "identity": json.Number("9007199254740993")})
		if err != nil {
			b.Fatal(err)
		}
		for _, fast := range []bool{false, true} {
			b.Run(fmt.Sprintf("paths%d/buffer%t", paths, fast), func(b *testing.B) {
				decode := decodeCallJSONReference
				if fast {
					decode = decodeCallJSON
				}
				b.SetBytes(int64(len(data)))
				b.ReportAllocs()
				for b.Loop() {
					var result map[string]any
					if err := decode(data, &result); err != nil {
						b.Fatal(err)
					}
					callJSONBenchmarkSink = result
				}
			})
		}
	}
}
