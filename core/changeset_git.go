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
	trimPath := func(fullPath, dir string) (string, bool) {
		relPath := strings.TrimPrefix(fullPath, dir)
		matched := relPath != fullPath
		relPath = strings.TrimPrefix(relPath, "/")
		return relPath, matched
	}
	trimPathIfPrefixed := func(fullPath, dir string) string {
		relPath, found := strings.CutPrefix(fullPath, dir)
		if !found {
			return ""
		}
		relPath = strings.TrimPrefix(relPath, "/")
		return relPath
	}

	scanner := bufio.NewScanner(bytes.NewReader(output))
	for scanner.Scan() {
		line := scanner.Text()
		statusField, rest, ok := strings.Cut(line, "\t")
		if !ok || statusField == "" {
			continue
		}

		status := statusField[0]
		switch status {
		case 'R':
			// Format: R100<tab>old_path<tab>new_path
			oldFull, newFull, ok := strings.Cut(rest, "\t")
			if !ok {
				continue
			}
			if oldPath := trimPathIfPrefixed(oldFull, beforeDir); oldPath != "" {
				result.Removed = append(result.Removed, oldPath)
			}
			if newPath := trimPathIfPrefixed(newFull, afterDir); newPath != "" {
				result.Added = append(result.Added, newPath)
			}
		case 'C':
			// Format: C100<tab>old_path<tab>new_path
			_, newFull, ok := strings.Cut(rest, "\t")
			if !ok {
				continue
			}
			if newPath := trimPathIfPrefixed(newFull, afterDir); newPath != "" {
				result.Added = append(result.Added, newPath)
			}
		case 'A':
			relPath, _ := trimPath(rest, afterDir)
			if relPath == "" {
				continue
			}
			result.Added = append(result.Added, relPath)
		case 'D':
			relPath, _ := trimPath(rest, beforeDir)
			if relPath == "" {
				continue
			}
			result.Removed = append(result.Removed, relPath)
		case 'M':
			relPath, matched := trimPath(rest, beforeDir)
			if !matched {
				relPath, _ = trimPath(rest, afterDir)
			}
			if relPath == "" {
				continue
			}
			result.Modified = append(result.Modified, relPath)
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
	beforeSet := make(map[string]struct{}, len(beforeDirs))
	for _, d := range beforeDirs {
		beforeSet[d] = struct{}{}
	}

	afterSet := make(map[string]struct{}, len(afterDirs))
	for _, d := range afterDirs {
		afterSet[d] = struct{}{}
	}

	for _, d := range afterDirs {
		if _, ok := beforeSet[d]; !ok {
			added = append(added, d)
		}
	}

	for _, d := range beforeDirs {
		if _, ok := afterSet[d]; !ok {
			removed = append(removed, d)
		}
	}

	return added, removed
}

// rollupRemovedPaths filters out paths that are children of removed directories.
// For example, if "dir/" is removed, we don't also list "dir/file.txt".
// Paths are sorted for deterministic output.
func rollupRemovedPaths(paths []string) []string {
	if len(paths) == 0 {
		return nil
	}

	// Sort to ensure parent directories come before their children
	slices.Sort(paths)

	var result []string
	var lastRemovedDir string

	for _, path := range paths {
		if lastRemovedDir != "" && strings.HasPrefix(path, lastRemovedDir) {
			continue
		}

		result = append(result, path)
		if strings.HasSuffix(path, "/") {
			lastRemovedDir = path
		}
	}

	return result
}
