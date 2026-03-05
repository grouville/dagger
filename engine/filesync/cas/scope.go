package cas

import (
	"encoding/json"
	"fmt"
	"path"
	"strings"

	digest "github.com/opencontainers/go-digest"
)

// ScopeInput is the canonical input set that identifies one filesync scope.
type ScopeInput struct {
	ClientPath      string
	IncludePatterns []string
	ExcludePatterns []string
	GitIgnore       bool
	RelativePath    string
}

type canonicalScopeInput struct {
	ClientPath      string   `json:"clientPath"`
	IncludePatterns []string `json:"includePatterns"`
	ExcludePatterns []string `json:"excludePatterns"`
	GitIgnore       bool     `json:"gitIgnore"`
	RelativePath    string   `json:"relativePath"`
}

// NewScopeKey builds a deterministic scope key from normalized scope inputs.
func NewScopeKey(input ScopeInput) (ScopeKey, error) {
	canonical, err := canonicalizeScopeInput(input)
	if err != nil {
		return "", err
	}

	payload, err := json.Marshal(canonical)
	if err != nil {
		return "", fmt.Errorf("marshal canonical scope: %w", err)
	}

	return ScopeKey(digest.FromBytes(payload).String()), nil
}

func canonicalizeScopeInput(input ScopeInput) (canonicalScopeInput, error) {
	clientPath, err := NormalizeScopePath(input.ClientPath)
	if err != nil {
		return canonicalScopeInput{}, fmt.Errorf("normalize client path: %w", err)
	}

	relativePath, err := NormalizeRelativePath(input.RelativePath)
	if err != nil {
		return canonicalScopeInput{}, fmt.Errorf("normalize relative path: %w", err)
	}

	return canonicalScopeInput{
		ClientPath:      clientPath,
		IncludePatterns: normalizePatternList(input.IncludePatterns),
		ExcludePatterns: normalizePatternList(input.ExcludePatterns),
		GitIgnore:       input.GitIgnore,
		RelativePath:    relativePath,
	}, nil
}

func normalizePatternList(patterns []string) []string {
	if len(patterns) == 0 {
		return []string{}
	}

	out := make([]string, 0, len(patterns))
	for _, pattern := range patterns {
		out = append(out, normalizeSlashes(pattern))
	}
	return out
}

// NormalizeScopePath normalizes the absolute client path used in a scope key.
func NormalizeScopePath(clientPath string) (string, error) {
	normalized := normalizeSlashes(strings.TrimSpace(clientPath))
	if normalized == "" {
		return "", fmt.Errorf("path is empty")
	}
	if !strings.HasPrefix(normalized, "/") {
		return "", fmt.Errorf("path must be absolute: %q", clientPath)
	}

	cleaned := path.Clean(normalized)
	if !strings.HasPrefix(cleaned, "/") {
		return "", fmt.Errorf("path escaped root: %q", clientPath)
	}

	return cleaned, nil
}

// NormalizeRelativePath normalizes optional relative path input.
func NormalizeRelativePath(relativePath string) (string, error) {
	normalized := normalizeSlashes(strings.TrimSpace(relativePath))
	if normalized == "" || normalized == "." {
		return "", nil
	}
	if strings.HasPrefix(normalized, "/") {
		return "", fmt.Errorf("relative path must not be absolute: %q", relativePath)
	}

	cleaned := path.Clean(normalized)
	if cleaned == "." {
		return "", nil
	}
	if cleaned == ".." || strings.HasPrefix(cleaned, "../") {
		return "", fmt.Errorf("relative path escapes root: %q", relativePath)
	}

	return cleaned, nil
}

// NormalizeEntryPath normalizes a manifest entry path and rejects path escapes.
func NormalizeEntryPath(entryPath string) (string, error) {
	normalized := normalizeSlashes(strings.TrimSpace(entryPath))
	if normalized == "" || normalized == "." {
		return "", fmt.Errorf("entry path is empty")
	}
	if strings.HasPrefix(normalized, "/") {
		return "", fmt.Errorf("entry path must not be absolute: %q", entryPath)
	}

	cleaned := path.Clean(normalized)
	if cleaned == "." {
		return "", fmt.Errorf("entry path is empty")
	}
	if cleaned == ".." || strings.HasPrefix(cleaned, "../") {
		return "", fmt.Errorf("entry path escapes root: %q", entryPath)
	}

	return cleaned, nil
}

func normalizeSlashes(value string) string {
	return strings.ReplaceAll(value, "\\", "/")
}
