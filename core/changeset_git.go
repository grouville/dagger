package core

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"io/fs"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
)

// gitDiffNameStatus runs `git diff --no-index --name-status` on two directories
// and returns the raw output. Exit code 1 (differences found) is not an error.
func gitDiffNameStatus(ctx context.Context, beforeDir, afterDir string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "git", "diff", "--no-index", "--name-status", beforeDir, afterDir)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
			// Exit code 1 means differences were found, which is expected
			return stdout.Bytes(), nil
		}
		return nil, err
	}

	return stdout.Bytes(), nil
}

// gitDiffQuiet runs `git diff --no-index --quiet` to check if directories differ.
// Returns true if directories are identical (no differences).
func gitDiffQuiet(ctx context.Context, beforeDir, afterDir string) (bool, error) {
	cmd := exec.CommandContext(ctx, "git", "diff", "--no-index", "--quiet", beforeDir, afterDir)

	if err := cmd.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
			// Exit code 1 means differences were found
			return false, nil
		}
		return false, err
	}

	// Exit code 0 means no differences
	return true, nil
}

// diffResult holds the parsed result of a git diff --name-status
type diffResult struct {
	Added    []string
	Modified []string
	Removed  []string
}

// parseGitDiffNameStatus parses the output of `git diff --no-index --name-status`.
// The beforeDir and afterDir are used to strip the absolute path prefixes from output.
//
// Git outputs lines like:
//
//	M       /path/to/before/file.txt
//	A       /path/to/after/newfile.txt
//	D       /path/to/before/deleted.txt
//	R100    /path/to/before/old.txt    /path/to/after/new.txt
func parseGitDiffNameStatus(output []byte, beforeDir, afterDir string) diffResult {
	var result diffResult

	scanner := bufio.NewScanner(bytes.NewReader(output))
	for scanner.Scan() {
		line := scanner.Text()
		if len(line) < 3 {
			continue
		}

		status := line[0]

		// Handle rename (R) and copy (C) which have two paths separated by tab
		// Format: R100<tab>old_path<tab>new_path
		if status == 'R' || status == 'C' {
			_, rest, ok := strings.Cut(line, "\t")
			if !ok {
				continue
			}
			oldFull, newFull, ok := strings.Cut(rest, "\t")
			if !ok {
				continue
			}
			if oldPath, found := strings.CutPrefix(oldFull, beforeDir); found {
				oldPath = strings.TrimPrefix(oldPath, "/")
				if oldPath != "" {
					result.Removed = append(result.Removed, oldPath)
				}
			}
			if newPath, found := strings.CutPrefix(newFull, afterDir); found {
				newPath = strings.TrimPrefix(newPath, "/")
				if newPath != "" {
					result.Added = append(result.Added, newPath)
				}
			}
			continue
		}

		// The path is after the status and a tab character
		fullPath := strings.TrimSpace(line[2:])

		// Strip the directory prefix to get the relative path
		var relPath string
		switch status {
		case 'A':
			// Added files show the "after" path
			relPath = strings.TrimPrefix(fullPath, afterDir)
		case 'D':
			// Deleted files show the "before" path
			relPath = strings.TrimPrefix(fullPath, beforeDir)
		case 'M':
			// Modified files could show either, but typically show "before" path
			relPath = strings.TrimPrefix(fullPath, beforeDir)
			if relPath == fullPath {
				relPath = strings.TrimPrefix(fullPath, afterDir)
			}
		default:
			continue
		}

		// Remove leading slash if present
		relPath = strings.TrimPrefix(relPath, "/")
		if relPath == "" {
			continue
		}

		switch status {
		case 'A':
			result.Added = append(result.Added, relPath)
		case 'M':
			result.Modified = append(result.Modified, relPath)
		case 'D':
			result.Removed = append(result.Removed, relPath)
		}
	}

	return result
}

// collectDirectories walks a directory tree and returns all directory paths
// relative to root, with trailing slashes (e.g., "subdir/nested/").
func collectDirectories(root string) ([]string, error) {
	var dirs []string

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() || path == root {
			return nil
		}

		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		dirs = append(dirs, rel+"/")
		return nil
	})

	return dirs, err
}

// diffDirectories compares two sets of directories and returns added and removed ones.
func diffDirectories(beforeDirs, afterDirs []string) (added, removed []string) {
	beforeSet := make(map[string]bool, len(beforeDirs))
	for _, d := range beforeDirs {
		beforeSet[d] = true
	}

	afterSet := make(map[string]bool, len(afterDirs))
	for _, d := range afterDirs {
		afterSet[d] = true
	}

	for _, d := range afterDirs {
		if !beforeSet[d] {
			added = append(added, d)
		}
	}

	for _, d := range beforeDirs {
		if !afterSet[d] {
			removed = append(removed, d)
		}
	}

	return added, removed
}

// rollupRemovedPaths filters out paths that are children of removed directories.
// For example, if "dir/" is removed, we don't also list "dir/file.txt".
// Input paths should be sorted for deterministic output.
func rollupRemovedPaths(paths []string) []string {
	if len(paths) == 0 {
		return nil
	}

	// Sort to ensure parent directories come before their children
	slices.Sort(paths)

	var result []string
	removedDirs := make(map[string]bool)

	for _, path := range paths {
		// Check if this path is under any already-removed directory
		skip := false
		for dir := range removedDirs {
			if strings.HasPrefix(path, dir) {
				skip = true
				break
			}
		}
		if skip {
			continue
		}

		// Track directories for child filtering
		if strings.HasSuffix(path, "/") {
			removedDirs[path] = true
		}

		result = append(result, path)
	}

	return result
}
