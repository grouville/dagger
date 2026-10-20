package workspace

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"slices"
	"strconv"
	"testing"

	"github.com/dagger/dagger/dagql"
)

// This compares only parsing/reuse after the same current bytes have been read.
// It is not a replacement implementation or an end-to-end command benchmark.
func BenchmarkGitClientCacheChoice(b *testing.B) {
	data, err := os.ReadFile("testdata/git-client-declarations.toml")
	if err != nil {
		b.Fatal(err)
	}
	for _, scenario := range []string{"repeated", "parallel", "distinct"} {
		b.Run(scenario, func(b *testing.B) {
			for _, choice := range []string{"lru", "dagql"} {
				b.Run(choice, func(b *testing.B) {
					ctx := b.Context()
					cache, err := dagql.NewCache(ctx, "", nil, nil)
					if err != nil {
						b.Fatal(err)
					}
					b.Cleanup(func() {
						if err := cache.ReleaseSession(context.Background(), "cache-choice"); err != nil {
							b.Error(err)
						}
						if err := cache.Close(context.Background()); err != nil {
							b.Error(err)
						}
					})
					decode := func(input []byte) gitClientDeclarations { return cachedGitClientDeclarations(input) }
					if choice == "dagql" {
						decode = func(input []byte) gitClientDeclarations {
							sum := sha256.Sum256(input)
							key := "workspace-git-client-declarations:" + hex.EncodeToString(sum[:])
							result, err := cache.GetOrInitArbitrary(ctx, "cache-choice", key, func(context.Context) (any, error) {
								return parseGitClientDeclarations(input), nil
							})
							if err != nil {
								b.Error(err)
								return gitClientDeclarations{}
							}
							return result.Value().(gitClientDeclarations)
						}
					}
					check := func(input []byte) {
						result := decode(input)
						logConfigWarnings(ctx, result.warnings)
						got := slices.Clone(result.scopes["."])
						if len(got) != 0 {
							b.Errorf("want no declared Git clients, got %v", got)
						}
					}
					check(data)
					b.ReportAllocs()
					b.ResetTimer()
					if scenario == "parallel" {
						b.RunParallel(func(pb *testing.PB) {
							for pb.Next() {
								check(data)
							}
						})
					} else {
						for i := range b.N {
							current := data
							if scenario == "distinct" {
								current = append(append([]byte(nil), data...), '\n', '#')
								current = strconv.AppendInt(current, int64(i), 10)
							}
							check(current)
						}
					}
					b.StopTimer()
				})
			}
		})
	}
}

func TestGitClientDagqlCacheLifetime(t *testing.T) {
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer cache.Close(context.Background())
	calls := 0
	load := func(session string) {
		_, err := cache.GetOrInitArbitrary(ctx, session, "declarations:lifetime", func(context.Context) (any, error) {
			calls++
			return gitClientDeclarations{}, nil
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	load("first")
	load("first")
	if calls != 1 {
		t.Fatalf("two lookups decoded %d times", calls)
	}
	if err := cache.ReleaseSession(ctx, "first"); err != nil {
		t.Fatal(err)
	}
	load("second")
	if calls != 2 {
		t.Fatalf("new session decoded %d total times; want 2", calls)
	}
	if err := cache.ReleaseSession(ctx, "second"); err != nil {
		t.Fatal(err)
	}
}
