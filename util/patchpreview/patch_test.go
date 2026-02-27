package patchpreview

import (
	"context"
	"strings"
	"testing"

	"github.com/muesli/termenv"
	"github.com/stretchr/testify/require"
)

type fakeChangeset struct {
	added    []string
	removed  []string
	modified []string
}

func (f fakeChangeset) AddedPaths(context.Context) ([]string, error) {
	return f.added, nil
}

func (f fakeChangeset) RemovedPaths(context.Context) ([]string, error) {
	return f.removed, nil
}

func (f fakeChangeset) ModifiedPaths(context.Context) ([]string, error) {
	return f.modified, nil
}

func TestNewFromChangesetPathsNoChanges(t *testing.T) {
	preview, err := NewFromChangesetPaths(context.Background(), fakeChangeset{})
	require.NoError(t, err)
	require.Nil(t, preview)
}

func TestNewFromChangesetPathsSummary(t *testing.T) {
	preview, err := NewFromChangesetPaths(context.Background(), fakeChangeset{
		added:    []string{"new.txt"},
		removed:  []string{"old.txt"},
		modified: []string{"mod.txt"},
	})
	require.NoError(t, err)
	require.NotNil(t, preview)

	var summary strings.Builder
	out := termenv.NewOutput(&summary, termenv.WithProfile(termenv.Ascii))
	require.NoError(t, preview.Summarize(out, 80))

	text := summary.String()
	require.Contains(t, text, "new.txt")
	require.Contains(t, text, "old.txt")
	require.Contains(t, text, "mod.txt")
	require.Contains(t, text, "3 files changed")
}
