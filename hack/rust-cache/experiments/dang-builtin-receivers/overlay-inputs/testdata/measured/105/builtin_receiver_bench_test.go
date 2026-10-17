package dang

import (
	"context"
	"testing"

	"github.com/vito/dang/v2/pkg/hm"
)

func BenchmarkBuiltinReceiverExpression(b *testing.B) {
	for _, scenario := range []struct{ name, source, want string }{
		{"string", `"prefix/value".hasPrefix("prefix/")`, "true"},
		{"list-block", `["a", "b", "c"].map { s => s + "!" }`, "[a!, b!, c!]"},
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
			first, err := EvalNode(ctx, scope, forms[0])
			if err != nil {
				b.Fatal(err)
			}
			if got := first.String(); got != scenario.want {
				b.Fatalf("got %s, want %s", got, scenario.want)
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
			if result.String() != scenario.want {
				b.Fatalf("got %s, want %s", result.String(), scenario.want)
			}
		})
	}
}
