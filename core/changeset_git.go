package core

import (
	"bytes"
	"context"
	"errors"
	"io/fs"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
)

// gitDiffNameStatus runs `git diff --no-index --name-status -z` on two directories.
// Exit code 1 (differences found) is not an error.
func gitDiffNameStatus(ctx context.Context, beforeDir, afterDir string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "git", "diff", "--no-index", "--name-status", "-z", beforeDir, afterDir)
	out, err := cmd.Output()
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
			return out, nil
		}
		return nil, err
	}
	return out, nil
}

// gitDiffQuiet checks if directories differ using `git diff --no-index --quiet`.
// Returns true if identical (exit 0), false if different (exit 1).
func gitDiffQuiet(ctx context.Context, beforeDir, afterDir string) (bool, error) {
	cmd := exec.CommandContext(ctx, "git", "diff", "--no-index", "--quiet", beforeDir, afterDir)
	if err := cmd.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

// diffResult holds parsed git diff --name-status output.
type diffResult struct {
	Added    []string
	Modified []string
	Removed  []string
}

// parseGitDiffNameStatus parses NUL-delimited `git diff --name-status -z` output.
// Format: STATUS\0PATH\0 or STATUS\0OLD\0NEW\0 for renames/copies.
func parseGitDiffNameStatus(output []byte, beforeDir, afterDir string) diffResult {
	var result diffResult
	if len(output) == 0 {
		return result
	}

	tokens := bytes.Split(output, []byte{0})
	i := 0

	nextToken := func() string {
		for i < len(tokens) && len(tokens[i]) == 0 {
			i++
		}
		if i >= len(tokens) {
			return ""
		}
		t := string(tokens[i])
		i++
		return t
	}

	for {
		statusToken := nextToken()
		if statusToken == "" {
			break
		}
		status := statusToken[0]

		pathOne := nextToken()
		if pathOne == "" {
			break
		}

		var pathTwo string
		if status == 'R' || status == 'C' {
			pathTwo = nextToken()
			if pathTwo == "" {
				break
			}
		}

		switch status {
		case 'A':
			if rel := trimPrefix(pathOne, afterDir); rel != "" {
				result.Added = append(result.Added, rel)
			}
		case 'D':
			if rel := trimPrefix(pathOne, beforeDir); rel != "" {
				result.Removed = append(result.Removed, rel)
			}
		case 'M', 'T':
			rel := trimPrefix(pathOne, beforeDir)
			if rel == "" {
				rel = trimPrefix(pathOne, afterDir)
			}
			if rel != "" {
				result.Modified = append(result.Modified, rel)
			}
		case 'R':
			if rel := trimPrefix(pathOne, beforeDir); rel != "" {
				result.Removed = append(result.Removed, rel)
			}
			if rel := trimPrefix(pathTwo, afterDir); rel != "" {
				result.Added = append(result.Added, rel)
			}
		case 'C':
			if rel := trimPrefix(pathTwo, afterDir); rel != "" {
				result.Added = append(result.Added, rel)
			}
		}
	}

	return result
}

// trimPrefix removes base prefix from path, returning relative path without leading slash.
func trimPrefix(path, base string) string {
	rel, ok := strings.CutPrefix(path, base)
	if !ok {
		return ""
	}
	return strings.TrimPrefix(rel, "/")
}

// collectDirectories returns all directory paths relative to root with trailing slashes.
func collectDirectories(root string) ([]string, error) {
	var dirs []string
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || !d.IsDir() || path == root {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		dirs = append(dirs, filepath.ToSlash(rel)+"/")
		return nil
	})
	return dirs, err
}

// diffDirectories returns added and removed directories between two sets.
// O(N+M) time, O(N) space.
func diffDirectories(beforeDirs, afterDirs []string) (added, removed []string) {
	before := make(map[string]struct{}, len(beforeDirs))
	for _, d := range beforeDirs {
		before[d] = struct{}{}
	}

	for _, d := range afterDirs {
		if _, exists := before[d]; exists {
			delete(before, d)
		} else {
			added = append(added, d)
		}
	}

	for d := range before {
		removed = append(removed, d)
	}
	slices.Sort(removed)

	return added, removed
}

// rollupRemovedPaths filters out children of removed directories.
// e.g., ["dir/", "dir/file.txt"] becomes ["dir/"].
// Output is sorted for determinism.
func rollupRemovedPaths(paths []string) []string {
	if len(paths) == 0 {
		return nil
	}

	sorted := slices.Clone(paths)
	slices.Sort(sorted)

	result := make([]string, 0, len(sorted))
	var parentDir string

	for _, p := range sorted {
		if parentDir != "" && strings.HasPrefix(p, parentDir) {
			continue
		}
		result = append(result, p)
		if strings.HasSuffix(p, "/") {
			parentDir = p
		} else {
			parentDir = ""
		}
	}

	return result
}
