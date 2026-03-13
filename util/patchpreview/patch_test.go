package patchpreview

import (
	"strings"
	"testing"

	"github.com/muesli/termenv"
	"github.com/stretchr/testify/require"
)

func TestNewEmpty(t *testing.T) {
	require.Nil(t, New(nil))
	require.Nil(t, New([]Entry{{Path: ""}}))
}

func TestSummary(t *testing.T) {
	preview := New([]Entry{
		{Path: "mod.txt", Kind: "MODIFIED", Added: 1, Removed: 1},
		{Path: "new.txt", Kind: "ADDED", Added: 1},
		{Path: "old.txt", Kind: "REMOVED", Removed: 1},
		{Path: "removed-dir/", Kind: "REMOVED"},
		{Path: "removed-dir/file.txt", Kind: "REMOVED", Removed: 2},
	})
	require.NotNil(t, preview)

	var summary strings.Builder
	out := termenv.NewOutput(&summary, termenv.WithProfile(termenv.Ascii))
	require.NoError(t, preview.Summarize(out, 80))

	text := summary.String()
	require.Contains(t, text, "mod.txt")
	require.Contains(t, text, "new.txt")
	require.Contains(t, text, "old.txt")
	require.Contains(t, text, "removed-dir/")
	require.NotContains(t, text, "removed-dir/file.txt")
	require.Contains(t, text, "4 files changed")
	require.Contains(t, text, "+2")
	require.Contains(t, text, "-4")
}
