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

type PatchPreview struct {
	entries []Entry
}

const (
	entryKindAdded    = "ADDED"
	entryKindModified = "MODIFIED"
	entryKindRemoved  = "REMOVED"
)

// EntriesFromPaths builds a flat list of entries from categorized path slices.
func EntriesFromPaths(added, modified, removed []string) []Entry {
	entries := make([]Entry, 0, len(added)+len(modified)+len(removed))
	for _, p := range added {
		entries = append(entries, Entry{Path: p, Kind: entryKindAdded})
	}
	for _, p := range modified {
		entries = append(entries, Entry{Path: p, Kind: entryKindModified})
	}
	for _, p := range removed {
		entries = append(entries, Entry{Path: p, Kind: entryKindRemoved})
	}
	return entries
}

func New(entries []Entry) *PatchPreview {
	normalized := make([]Entry, 0, len(entries))
	for _, entry := range entries {
		if entry.Path == "" {
			continue
		}
		if entry.Kind == "" {
			entry.Kind = entryKindModified
		}
		normalized = append(normalized, entry)
	}
	if len(normalized) == 0 {
		return nil
	}

	normalized = consolidateRemovedDirs(normalized)
	// Normalize output order regardless of caller input ordering.
	slices.SortFunc(normalized, func(a, b Entry) int {
		return strings.Compare(a.Path, b.Path)
	})

	return &PatchPreview{entries: normalized}
}

func (preview *PatchPreview) Summarize(out *termenv.Output, maxWidth int) error {
	longestFilenameLen := 0
	for _, entry := range preview.entries {
		if len(entry.Path) > longestFilenameLen {
			longestFilenameLen = len(entry.Path)
		}
	}

	var maxFilenameLen int
	if maxWidth > 0 {
		maxFilenameLen = max(maxWidth-20, 10) // Leave space for " | ", change count, and bars
		if longestFilenameLen > maxFilenameLen {
			longestFilenameLen = maxFilenameLen
		}
	}

	totalAdded := 0
	totalRemoved := 0

	for _, entry := range preview.entries {
		filename := shortenPath(entry.Path, maxFilenameLen)

		var filenameColor termenv.Color
		switch entry.Kind {
		case entryKindAdded:
			filenameColor = termenv.ANSIGreen
		case entryKindRemoved:
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

		if maxWidth > 0 {
			if entry.Added > 0 {
				fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("+%d", entry.Added)).Foreground(termenv.ANSIGreen))
			}
			if entry.Removed > 0 {
				fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("-%d", entry.Removed)).Foreground(termenv.ANSIRed))
			}
		} else {
			out.WriteString(" | ")
			if entry.Added > 0 {
				out.WriteString(out.String(strings.Repeat("+", entry.Added)).Foreground(termenv.ANSIGreen).String())
			}
			if entry.Removed > 0 {
				out.WriteString(out.String(strings.Repeat("-", entry.Removed)).Foreground(termenv.ANSIRed).String())
			}
		}
		out.WriteString("\n")
	}

	fmt.Fprintln(out)
	fmt.Fprintf(out, "%d %s changed", len(preview.entries), pluralize(len(preview.entries), "file", "files"))
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

	return nil
}

func consolidateRemovedDirs(entries []Entry) []Entry {
	removedDirs := make([]Entry, 0, len(entries))
	otherEntries := make([]Entry, 0, len(entries))
	for _, entry := range entries {
		if entry.Kind == entryKindRemoved && strings.HasSuffix(entry.Path, "/") {
			removedDirs = append(removedDirs, entry)
			continue
		}
		otherEntries = append(otherEntries, entry)
	}
	if len(removedDirs) == 0 {
		return entries
	}

	result := make([]Entry, 0, len(otherEntries)+len(removedDirs))
entryLoop:
	for _, entry := range otherEntries {
		if entry.Kind == entryKindRemoved {
			for i := range removedDirs {
				if strings.HasPrefix(entry.Path, removedDirs[i].Path) {
					removedDirs[i].Removed += entry.Removed
					continue entryLoop
				}
			}
		}
		result = append(result, entry)
	}

	result = append(result, removedDirs...)
	return result
}

func pluralize(count int, singular, plural string) string {
	if count == 1 {
		return singular
	}
	return plural
}

func shortenPath(filename string, maxFilenameLen int) string {
	if maxFilenameLen == 0 {
		return filename
	}
	if len(filename) > maxFilenameLen {
		filename = "..." + filename[len(filename)-(maxFilenameLen-3):]
	}
	return filename
}
