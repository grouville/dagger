package dagql

import (
	"fmt"
	"math"
	"testing"

	"github.com/stretchr/testify/require"
)

// Keep the generic Enumerable path available as an independent encoding oracle.
type persistedGenericArray struct {
	Typed
	Enumerable
}

func TestPersistedPrimitiveArrayEncoding(t *testing.T) {
	for _, tc := range []struct {
		name  string
		value Typed
	}{
		{"strings", Array[String]{"", "é\n\"\\", "<html>"}},
		{"ints", Array[Int]{math.MinInt64, 9007199254740993, math.MaxInt64}},
		{"floats", Array[Float]{Float(math.Copysign(0, -1)), 1e-300, 1e300}},
		{"booleans", Array[Boolean]{true, false}},
		{"empty strings", Array[String]{}},
		{"empty ints", Array[Int]{}},
		{"empty floats", Array[Float]{}},
		{"empty booleans", Array[Boolean]{}},
		{"nan", Array[Float]{1, Float(math.NaN())}},
		{"infinity", Array[Float]{1, Float(math.Inf(1))}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			frame := persistCodecFrame("values", tc.value)
			res, err := NewResultForCall(tc.value, frame)
			require.NoError(t, err)
			generic := persistedGenericArray{tc.value, tc.value.(Enumerable)}
			reference, err := NewResultForCall(generic, frame)
			require.NoError(t, err)

			want, wantErr := DefaultPersistedSelfCodec.EncodeResult(t.Context(), nil, reference)
			got, err := DefaultPersistedSelfCodec.EncodeResult(t.Context(), nil, res)
			if wantErr != nil {
				require.EqualError(t, err, wantErr.Error())
				return
			}
			require.NoError(t, err)
			require.Equal(t, want, got, "item types, identities and resource links must remain unchanged")

		})
	}
}

func BenchmarkPersistedPrimitiveArray(b *testing.B) {
	for _, size := range []int{128, 512, 1024} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			values := make(Array[String], size)
			inputs := make([]*ResultCallLiteral, size)
			for i := range size {
				values[i] = String(fmt.Sprintf("digest-%d", i))
				inputs[i] = &ResultCallLiteral{Kind: ResultCallLiteralKindString, StringValue: fmt.Sprintf("crate_%04d", i)}
			}
			frame := persistCodecFrame("digests", values)
			frame.Args = []*ResultCallArg{{Name: "paths", Value: &ResultCallLiteral{Kind: ResultCallLiteralKindList, ListItems: inputs}}}
			res := newDetachedResult(frame, values)
			b.ReportAllocs()
			for b.Loop() {
				encoded, err := DefaultPersistedSelfCodec.EncodeResult(b.Context(), nil, res)
				if err != nil || len(encoded.Envelope.Items) != size {
					b.Fatalf("items=%d, error=%v", len(encoded.Envelope.Items), err)
				}
			}
		})
	}
}
