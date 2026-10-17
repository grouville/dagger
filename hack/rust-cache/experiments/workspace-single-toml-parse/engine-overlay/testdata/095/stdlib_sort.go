package dang

import (
	"context"
	"slices"
	"strings"

	"github.com/vito/dang/v2/pkg/hm"
)

func registerStringSorting() {
	Builtin("sortStrings").
		Doc("returns a new list of strings in ascending UTF-8 byte order, preserving duplicates").
		Example(`sortStrings(["b", "a", "b"])`).
		Params("items", NonNull(ListOf(NonNull(StringType)))).
		Returns(NonNull(ListOf(NonNull(StringType)))).
		Impl(func(ctx context.Context, args Args) (Value, error) {
			if err := ctx.Err(); err != nil {
				return nil, err
			}
			items := slices.Clone(args.GetList("items"))
			slices.SortFunc(items, func(a, b Value) int {
				return strings.Compare(a.(StringValue).Val, b.(StringValue).Val)
			})
			return ListValue{Elements: items, ElemType: hm.NonNullType{Type: StringType}}, nil
		})
}
