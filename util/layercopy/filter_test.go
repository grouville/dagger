package layercopy

import (
	"fmt"
	"path/filepath"
	"testing"

	"github.com/moby/patternmatcher"
	"github.com/stretchr/testify/require"
)

func TestIncludePathInheritsPositiveMatch(t *testing.T) {
	for _, filter := range []Filter{
		{Include: []string{"root", "root/b/keep"}},
		{Include: []string{"root/**", "root/b/**"}, Exclude: []string{"root/b/private"}},
		{Include: []string{"root"}, Only: map[string]struct{}{"root/b/keep": {}}},
		{Include: []string{"root", "!root/b", "root/b/keep"}},
	} {
		m, err := newMatcher("/", filter)
		require.NoError(t, err)
		reference, err := patternmatcher.New(filter.Include)
		require.NoError(t, err)
		states := map[string]matchState{}
		parents := map[string]patternmatcher.MatchInfo{}
		for _, rel := range []string{
			"root", "root/b", "root/b/keep", "root/b/private", "root/b/private/file",
			"root/c", "root/c/file", "other", "other/file",
		} {
			parent := filepath.Dir(rel)
			want, info, err := reference.MatchesUsingParentResults(rel, parents[parent])
			require.NoError(t, err)
			parents[rel] = info
			if filter.Only != nil {
				_, selected := filter.Only[rel]
				want = want && selected
			}
			if m.exclude != nil {
				excluded, err := m.exclude.MatchesOrParentMatches(rel)
				require.NoError(t, err)
				want = want && !excluded
			}
			got, state, err := m.includePath(rel, "/"+rel, nil, states[parent])
			require.NoError(t, err)
			states[rel] = state
			require.Equal(t, want, got, "filter %v, path %s", filter, rel)
		}
	}
}

func BenchmarkIncludePathMatchedSubtree(b *testing.B) {
	for _, count := range []int{1, 16, 128, 1024} {
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			patterns := make([]string, count)
			for i := range patterns {
				patterns[i] = fmt.Sprintf("crate%04d/**", i)
			}
			m, err := newMatcher("/", Filter{Include: patterns})
			require.NoError(b, err)
			parent := fmt.Sprintf("crate%04d/session", count-1)
			matched, state, err := m.includePath(parent, "/"+parent, nil, matchState{})
			require.NoError(b, err)
			require.True(b, matched)
			rel := parent + "/query-cache.bin"
			abs := "/" + rel
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				matched, _, err := m.includePath(rel, abs, nil, state)
				if err != nil || !matched {
					b.Fatalf("match: %v, %v", matched, err)
				}
			}
		})
	}
}
