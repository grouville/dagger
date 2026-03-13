package patchpreview

import (
	"fmt"
	"slices"
	"strings"

	"github.com/muesli/termenv"
)

type Entry struct {
	Path    string
	Kind    string
	Added   int
	Removed int
}

// Kind constants categorize how a path changed between two directory snapshots.
const (
	KindAdded    = "ADDED"
	KindModified = "MODIFIED"
	KindRemoved  = "REMOVED"
)

type PatchPreview struct {
	entries []Entry
}

func New(entries []Entry) *PatchPreview {
	if len(entries) == 0 {
		return nil
	}

	entries = consolidateRemovedDirs(entries)
	slices.SortFunc(entries, func(a, b Entry) int {
		return strings.Compare(a.Path, b.Path)
	})

	return &PatchPreview{entries: entries}
}

func (preview *PatchPreview) Summarize(out *termenv.Output, maxWidth int) {
	maxFilenameLen := max(maxWidth-20, 10)

	longestFilenameLen := 0
	for _, entry := range preview.entries {
		if l := len(entry.Path); l > longestFilenameLen {
			longestFilenameLen = l
		}
	}
	if longestFilenameLen > maxFilenameLen {
		longestFilenameLen = maxFilenameLen
	}

	totalAdded := 0
	totalRemoved := 0

	for _, entry := range preview.entries {
		filename := entry.Path
		if len(filename) > maxFilenameLen {
			filename = "..." + filename[len(filename)-(maxFilenameLen-3):]
		}

		var filenameColor termenv.Color
		switch entry.Kind {
		case KindAdded:
			filenameColor = termenv.ANSIGreen
		case KindRemoved:
			filenameColor = termenv.ANSIRed
		default:
			filenameColor = termenv.ANSIYellow
		}

		totalAdded += entry.Added
		totalRemoved += entry.Removed

		out.WriteString(out.String(filename).Foreground(filenameColor).String())
		if len(filename) < longestFilenameLen {
			out.WriteString(strings.Repeat(" ", longestFilenameLen-len(filename)))
		}

		if entry.Added > 0 {
			fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("+%d", entry.Added)).Foreground(termenv.ANSIGreen))
		}
		if entry.Removed > 0 {
			fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("-%d", entry.Removed)).Foreground(termenv.ANSIRed))
		}
		out.WriteString("\n")
	}

	fileWord := "files"
	if len(preview.entries) == 1 {
		fileWord = "file"
	}
	fmt.Fprintf(out, "\n%d %s changed", len(preview.entries), fileWord)
	if totalAdded+totalRemoved > 0 {
		fmt.Fprint(out, ",")
		if totalAdded > 0 {
			out.WriteString(out.String(fmt.Sprintf(" +%d", totalAdded)).Foreground(termenv.ANSIGreen).String())
		}
		if totalRemoved > 0 {
			out.WriteString(out.String(fmt.Sprintf(" -%d", totalRemoved)).Foreground(termenv.ANSIRed).String())
		}
		out.WriteString(" lines")
	}
}

// consolidateRemovedDirs folds removed files into their parent removed
// directory, summing line counts. E.g. if "dir/" and "dir/file.txt" are
// both removed, only "dir/" is kept with the combined line count.
func consolidateRemovedDirs(entries []Entry) []Entry {
	// Collect removed directories (paths ending in "/").
	var removedDirs []Entry
	for _, entry := range entries {
		if entry.Kind == KindRemoved && strings.HasSuffix(entry.Path, "/") {
			removedDirs = append(removedDirs, entry)
		}
	}
	if len(removedDirs) == 0 {
		return entries
	}

	// Build a set of removed-dir prefixes for O(d*n) matching.
	result := make([]Entry, 0, len(entries))
	for _, entry := range entries {
		if entry.Kind == KindRemoved && !strings.HasSuffix(entry.Path, "/") {
			folded := false
			for i := range removedDirs {
				if strings.HasPrefix(entry.Path, removedDirs[i].Path) {
					removedDirs[i].Removed += entry.Removed
					folded = true
					break
				}
			}
			if folded {
				continue
			}
		}
		// Keep non-removed entries and directory entries themselves.
		// Directory entries will be replaced by the updated removedDirs below.
		if entry.Kind == KindRemoved && strings.HasSuffix(entry.Path, "/") {
			continue
		}
		result = append(result, entry)
	}

	return append(result, removedDirs...)
}
