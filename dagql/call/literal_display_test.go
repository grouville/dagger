package call

import (
	"fmt"
	"testing"
)

func TestCompositeLiteralDisplay(t *testing.T) {
	tests := []struct {
		name string
		lit  Literal
		want string
	}{
		{"empty list", NewLiteralList(), "[]"},
		{"empty object", NewLiteralObject(), "{}"},
		{"nested", NewLiteralObject(
			NewArgument("z", NewLiteralList(NewLiteralBool(true), NewLiteralInt(-2), NewLiteralString("quote\"\\\n雪")), false),
			NewArgument("a", NewLiteralObject(), false),
		), `{z: [true,-2,"quote\"\\\n雪"],a: {}}`},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := test.lit.Display(); got != test.want {
				t.Fatalf("display = %q, want %q", got, test.want)
			}
		})
	}
}

var literalDisplayResult string

func BenchmarkCompositeLiteralDisplay(b *testing.B) {
	for _, size := range []int{128, 512, 1024} {
		values := make([]Literal, size)
		fields := make([]*Argument, size)
		for i := range size {
			values[i] = NewLiteralString(fmt.Sprintf("sha256:%064x", i))
			fields[i] = NewArgument(fmt.Sprintf("field_%04d", i), values[i], false)
		}
		for _, shape := range []struct {
			name string
			lit  Literal
		}{{"list", NewLiteralList(values...)}, {"object", NewLiteralObject(fields...)}} {
			b.Run(fmt.Sprintf("%s/%d", shape.name, size), func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					literalDisplayResult = shape.lit.Display()
				}
			})
		}
	}
}
