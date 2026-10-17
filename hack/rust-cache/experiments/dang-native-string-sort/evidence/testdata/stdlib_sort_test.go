package dang

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSortStrings(t *testing.T) {
	require.NoError(t, evalExample(`
let paths = ["é", "a/b.go", "a.go", "_", "A", "", "a.go", "é", "\n"]
let result = sortStrings(paths)
assert { result == ["", "\n", "A", "_", "a.go", "a.go", "a/b.go", "é", "é"] }
assert { paths == ["é", "a/b.go", "a.go", "_", "A", "", "a.go", "é", "\n"] }
assert { sortStrings([]) == [] }
assert { sortStrings(["only"]) == ["only"] }
`))
	for _, source := range []string{`sortStrings([1, 2])`, `sortStrings(["a", null])`} {
		err := evalExample(source)
		require.Error(t, err)
		require.Contains(t, err.Error(), "type:")
	}
}

// Keep the module's original helper here so both algorithms run through the
// same interpreter and receive the same inputs and argument-binding work.
const moduleStringSort = `
let original(items: [String!]!): [String!]! {
  let empty: [String!]! = []
  items.reduce(empty) { acc, item =>
    if (acc.length == 0 or acc.takeLast(1).join("") <= item) {
      acc + [item]
    } else {
      acc.takeWhile { x => x <= item } + [item] + acc.dropWhile { x => x <= item }
    }
  }
}
let native(items: [String!]!): [String!]! { sortStrings(items) }
`

var benchmarkSortedStrings Value

func BenchmarkModuleStringSort(b *testing.B) {
	dir := b.TempDir()
	require.NoError(b, os.WriteFile(filepath.Join(dir, "main.dang"), []byte(moduleStringSort), 0600))
	env, err := RunDir(context.Background(), dir, false)
	require.NoError(b, err)
	for _, count := range []int{8, 128, 512} {
		for _, order := range []string{"sorted", "reverse", "shuffled"} {
			strings := make([]string, count)
			for i := range strings {
				strings[i] = fmt.Sprintf("pkg/%06d/file.go", i)
			}
			if order == "reverse" {
				slices.Reverse(strings)
			} else if order == "shuffled" {
				rand.New(rand.NewSource(20261016)).Shuffle(len(strings), func(i, j int) {
					strings[i], strings[j] = strings[j], strings[i]
				})
			}
			input, err := ToValue(strings)
			require.NoError(b, err)
			for _, name := range []string{"original", "native"} {
				fn, found, err := env.Lookup(context.Background(), name)
				require.NoError(b, err)
				require.True(b, found)
				callable := fn.(Callable)
				check, err := callable.Call(context.Background(), env, map[string]Value{"items": input})
				require.NoError(b, err)
				actual := make([]string, 0, count)
				for _, value := range check.(ListValue).Elements {
					actual = append(actual, value.(StringValue).Val)
				}
				expected := slices.Clone(strings)
				slices.Sort(expected)
				require.Equal(b, expected, actual)
				b.Run(fmt.Sprintf("%s/%s/%d", name, order, count), func(b *testing.B) {
					args := map[string]Value{"items": input}
					b.ReportAllocs()
					for b.Loop() {
						result, err := callable.Call(context.Background(), env, args)
						if err != nil {
							b.Fatal(err)
						}
						benchmarkSortedStrings = result
					}
				})
			}
		}
	}
}
