package patternmatcher

import (
	"fmt"
	"strings"
	"testing"
)

func TestLiteralSuffixMatchesRegexp(t *testing.T) {
	patterns := []string{
		"**/*.go", "*.go", "module/**/*.go", "a/**/b?.go", "**/*.go*", "**/*^.go",
		"**/*[a-c].go", `**/\n`, `**/\*.go`, "**/*é.go", "**/*�.go", "**/*.$",
	}
	paths := []string{"", "file.go", "file.rs", "file.go/", "file.go/child", ".go", "a/.go", "a/bc.go", "module/a/b.go", "module/a/b.txt", "a/é.go", "a/�.go", "a/\xff.go", "a/\n", "a/n", "a/*.go", "a/file.$"}
	for depth := range 8 {
		for _, extension := range []string{".go", ".rs", ".go.tmp", ".txt"} {
			paths = append(paths, strings.Repeat("some-directory/", depth)+"file"+extension)
		}
	}
	for _, pattern := range patterns {
		for _, exclude := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/exclude=%t", pattern, exclude), func(t *testing.T) {
				input := pattern
				if exclude {
					input = "!" + input
				}
				p, err := NewPattern(input)
				if err != nil {
					t.Fatal(err)
				}
				if err := p.compile("/"); err != nil {
					t.Fatal(err)
				}
				if p.regexp == nil {
					t.Fatal("test requires a regexp pattern")
				}
				for _, path := range paths {
					want := p.regexp.MatchString(path)
					got, err := p.match(path)
					if err != nil || got != want {
						t.Errorf("match(%q)=%t,%v; regexp=%t", path, got, err, want)
					}
					public, err := p.Match(path)
					if err != nil || public != (want && !exclude) {
						t.Errorf("Match(%q)=%t,%v", path, public, err)
					}
				}
			})
		}
	}
}

var literalSuffixMatchSink bool

func BenchmarkLiteralSuffix(b *testing.B) {
	for _, path := range []string{"short.txt", strings.Repeat("some-directory/", 8) + "file.txt", strings.Repeat("some-directory/", 8) + "file.go"} {
		b.Run(path, func(b *testing.B) {
			p, err := NewPattern("**/*.go")
			if err != nil {
				b.Fatal(err)
			}
			if _, err := p.Match(path); err != nil {
				b.Fatal(err)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				matched, err := p.Match(path)
				if err != nil {
					b.Fatal(err)
				}
				literalSuffixMatchSink = matched
			}
		})
	}
}
