package dang

import (
	"context"
	"github.com/vito/dang/v2/pkg/hm"
	"testing"
)

func BenchmarkBuiltinReceiverExpression(b *testing.B) {
	for _, scenario := range []struct{ name, source string }{
		{"string", `"prefix/value".hasPrefix("prefix/")`},
		{"list-block", `["a", "b", "c"].map { s => s + "!" }`},
	} {
		b.Run(scenario.name, func(b *testing.B) {
			source := scenario.source
			parsed, err := ParseWithRecovery("receiver-bench", []byte(source))
			if err != nil {
				b.Fatal(err)
			}
			forms := parsed.(*FileBlock).Forms
			types, scope := BuildScopesFromImports("", nil)
			ctx := context.Background()
			if _, err := InferFormsWithPhases(ctx, forms, types, hm.NewSimpleFresher()); err != nil {
				b.Fatal(err)
			}
			expected, err := EvalNode(ctx, scope, forms[0])
			if err != nil {
				b.Fatal(err)
			}
			var result Value
			b.ReportAllocs()
			b.ResetTimer()
			for range b.N {
				result, err = EvalNode(ctx, scope, forms[0])
				if err != nil {
					b.Fatal(err)
				}
			}
			b.StopTimer()
			if result.String() != expected.String() {
				b.Fatalf("got %s, want %s", result.String(), expected.String())
			}
		})
	}
}
