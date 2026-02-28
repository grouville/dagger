package patchpreview

import (
	"fmt"
	"slices"
	"strings"

	"github.com/jedevc/diffparser"
	"github.com/muesli/termenv"
)

type Entry struct {
	Path    string
	Kind    string
	Added   int
	Removed int
}

type PatchPreview struct {
	lines []patchPreviewLine
}

func New(entries []Entry) *PatchPreview {
	if len(entries) == 0 {
		return nil
	}

	lines := make([]patchPreviewLine, 0, len(entries))
	for _, entry := range entries {
		if entry.Path == "" {
			continue
		}
		lines = append(lines, patchPreviewLine{
			filename: entry.Path,
			mode:     modeFromKind(entry.Kind),
			added:    entry.Added,
			removed:  entry.Removed,
		})
	}
	if len(lines) == 0 {
		return nil
	}

	lines = consolidateRemovedDirs(lines)
	slices.SortFunc(lines, func(a, b patchPreviewLine) int {
		return strings.Compare(a.filename, b.filename)
	})

	return &PatchPreview{lines: lines}
}

func (preview *PatchPreview) Summarize(out *termenv.Output, maxWidth int) error {
	lines := preview.lines

	longestFilenameLen := 0
	for _, line := range lines {
		if len(line.filename) > longestFilenameLen {
			longestFilenameLen = len(line.filename)
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

	for _, line := range lines {
		filename := shortenPath(line.filename, maxFilenameLen)

		var filenameColor termenv.Color
		switch line.mode {
		case diffparser.NEW:
			filenameColor = termenv.ANSIGreen
		case diffparser.DELETED:
			filenameColor = termenv.ANSIRed
		case diffparser.MODIFIED, diffparser.RENAMED:
			filenameColor = termenv.ANSIYellow
		}

		totalAdded += line.added
		totalRemoved += line.removed

		out.WriteString(out.String(filename).Foreground(filenameColor).String())
		if len(filename) < longestFilenameLen {
			out.WriteString(strings.Repeat(" ", longestFilenameLen-len(filename)))
		}

		if maxWidth > 0 {
			if line.added > 0 {
				fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("+%d", line.added)).Foreground(termenv.ANSIGreen))
			}
			if line.removed > 0 {
				fmt.Fprintf(out, " %s", out.String(fmt.Sprintf("-%d", line.removed)).Foreground(termenv.ANSIRed))
			}
		} else {
			out.WriteString(" | ")
			if line.added > 0 {
				out.WriteString(out.String(strings.Repeat("+", line.added)).Foreground(termenv.ANSIGreen).String())
			}
			if line.removed > 0 {
				out.WriteString(out.String(strings.Repeat("-", line.removed)).Foreground(termenv.ANSIRed).String())
			}
		}
		out.WriteString("\n")
	}

	fmt.Fprintln(out)
	fmt.Fprintf(out, "%d %s changed", len(lines), pluralize(len(lines), "file", "files"))
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

type patchPreviewLine struct {
	filename string
	mode     diffparser.FileMode
	added    int
	removed  int
}

func consolidateRemovedDirs(lines []patchPreviewLine) []patchPreviewLine {
	removedDirs := make([]patchPreviewLine, 0, len(lines))
	otherLines := make([]patchPreviewLine, 0, len(lines))
	for _, line := range lines {
		if line.mode == diffparser.DELETED && strings.HasSuffix(line.filename, "/") {
			removedDirs = append(removedDirs, line)
			continue
		}
		otherLines = append(otherLines, line)
	}
	if len(removedDirs) == 0 {
		return lines
	}

	result := make([]patchPreviewLine, 0, len(otherLines)+len(removedDirs))
lineLoop:
	for _, line := range otherLines {
		if line.mode == diffparser.DELETED {
			for i := range removedDirs {
				if strings.HasPrefix(line.filename, removedDirs[i].filename) {
					removedDirs[i].removed += line.removed
					continue lineLoop
				}
			}
		}
		result = append(result, line)
	}

	result = append(result, removedDirs...)
	return result
}

func modeFromKind(kind string) diffparser.FileMode {
	switch kind {
	case "ADDED":
		return diffparser.NEW
	case "REMOVED":
		return diffparser.DELETED
	default:
		return diffparser.MODIFIED
	}
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
