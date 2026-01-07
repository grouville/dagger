// Shared logic for managing Dagger versions
//
// In general, it attempts to follow go's psedudoversioning:
// https://go.dev/doc/modules/version-numbers
package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/dagger/dagger/version/internal/dagger"
	"golang.org/x/mod/semver"
)

func New(
	// A git repository containing the source code of the artifact to be versioned.
	// +optional
	// +defaultPath="/.git"
	git *dagger.Directory,

	// A directory containing all the inputs of the artifact to be versioned.
	// An input is any file that changes the artifact if it changes.
	// This directory is used to compute a digest. If any input changes, the digest changes.
	// - To avoid false positives, only include actual inputs
	// - To avoid false negatives, include *all* inputs
	// +optional
	// +defaultPath="/"
	// +ignore=["**_test.go", "**/.git*", "**/.venv", "**/.dagger", ".*", "bin", "**/node_modules", "**/testdata/**", "**/.changes", ".changes", "docs", "helm", "release", "version", "modules", "*.md", "LICENSE", "NOTICE", "hack"]
	inputs *dagger.Directory,

	// File containing the next release version (e.g. .changes/.next)
	// +optional
	// +defaultPath="/.changes/.next"
	nextVersionFile *dagger.File,
) *Version {
	return &Version{
		Git:             git.AsGit(),
		GitDir:          git,
		Inputs:          inputs,
		NextVersionFile: nextVersionFile,
	}
}

type Version struct {
	// +private
	Git    *dagger.GitRepository
	GitDir *dagger.Directory

	// +private
	Inputs *dagger.Directory

	// +private
	NextVersionFile *dagger.File
}

// Generate a version string from the current context
func (v Version) Version(ctx context.Context) (string, error) {
	dirty, err := v.Dirty(ctx)
	if err != nil {
		return "", err
	}

	if dirty {
		// this is a dirty version - git state is dirty
		// (v<major>.<minor>.<patch>-<timestamp>-dev-<inputdigest>)
		next, err := v.NextReleaseVersion(ctx)
		if err != nil {
			return "", err
		}
		rawDigest, err := v.Inputs.Digest(ctx)
		if err != nil {
			return "", err
		}
		_, digest, ok := strings.Cut(rawDigest, ":")
		if !ok {
			return "", fmt.Errorf("invalid digest: %s", rawDigest)
		}
		return fmt.Sprintf("%s-%s-dev-%s", next, pseudoversionTimestamp(time.Now()), digest[:12]), nil
	}

	if tag, err := v.CurrentTag(ctx); err != nil {
		return "", err
	} else if tag != "" {
		// this is a tagged release
		// (v<major>.<minor>.<patch>)
		return tag, nil
	}

	// this is a clean, untagged version - git state is clean, but no tag
	// (v<major>.<minor>.<patch>-<timestamp>-dev-<commit>)
	next, err := v.NextReleaseVersion(ctx)
	if err != nil {
		return "", err
	}
	head := v.Git.Head()
	commit, err := head.Commit(ctx)
	if err != nil {
		return "", err
	}
	commitDate, err := refTimestamp(ctx, head)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s-%s-dev-%s", next, pseudoversionTimestamp(commitDate), commit[:12]), nil
}

// Return the tag to use when auto-downloading the engine image from the CLI
func (v Version) ImageTag(ctx context.Context) (string, error) {
	if tag, err := v.CurrentTag(ctx); err != nil {
		return "", err
	} else if tag != "" {
		// this is a tagged release
		// (v<major>.<minor>.<patch>)
		return tag, nil
	}

	// For untagged builds, find merge-base with main
	// Try local main first, then origin/main for CI (detached HEAD)
	head := v.Git.Head()
	for _, ref := range []string{"main", "origin/main"} {
		if branch := v.Git.Branch(ref); branch != nil {
			if mergeBase, err := head.CommonAncestor(branch).Commit(ctx); err == nil {
				return mergeBase, nil
			}
		}
	}
	return head.Commit(ctx)
}

func (v Version) Dirty(ctx context.Context) (bool, error) {
	checkout := v.Git.Head().Tree()
	changes := v.Inputs.Changes(checkout)
	isEmpty, err := changes.IsEmpty(ctx)
	if err != nil {
		return false, err
	}
	return !isEmpty, nil
}

func (v Version) CurrentTag(ctx context.Context) (string, error) {
	commit, err := v.Git.Head().Commit(ctx)
	if err != nil {
		return "", err
	}
	tags, err := v.tagsAtCommit(ctx, commit)
	if err != nil {
		return "", err
	}
	for _, tag := range tags {
		if semver.IsValid(tag) {
			return tag, nil
		}
	}
	return "", nil
}

func (v Version) tagsAtCommit(ctx context.Context, commit string) ([]string, error) {
	// NOTE: this uses the git dir directly rather than the git repo
	// since there's no dagger API to do this operation
	out, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".git", v.GitDir).
		WithExec([]string{"git", "tag", "-l", "--points-at=" + commit}).
		Stdout(ctx)
	if err != nil {
		return nil, err
	}
	out = strings.TrimSpace(out)
	if out == "" {
		return nil, nil
	}
	return strings.Split(out, "\n"), nil
}

func refTimestamp(ctx context.Context, head *dagger.GitRef) (time.Time, error) {
	checkout := head.Tree()
	status, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".", checkout).
		WithExec([]string{"git", "log", "-1", "--format=%cI"}).
		Stdout(ctx)
	if err != nil {
		return time.Time{}, err
	}
	status = strings.TrimSpace(status)
	t, err := time.Parse(time.RFC3339, status)
	if err != nil {
		return time.Time{}, err
	}
	return t, nil
}

func pseudoversionTimestamp(t time.Time) string {
	// go time formatting is bizarre - this translates to "yyyymmddhhmmss"
	// inspired from: https://cs.opensource.google/go/x/mod/+/refs/tags/v0.22.0:module/pseudo.go
	return t.UTC().Format("20060102150405")
}

// NextReleaseVersion returns the next release version from .changes/.next
func (v Version) NextReleaseVersion(ctx context.Context) (string, error) {
	if v.NextVersionFile == nil {
		return "", fmt.Errorf("next version file not provided")
	}
	content, err := v.NextVersionFile.Contents(ctx)
	if err != nil {
		return "", err
	}
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "v") && semver.IsValid(line) {
			return line, nil
		}
	}
	return "", fmt.Errorf("no valid version found in next version file")
}

// DebugDirtyInfo returns detailed information about the dirty detection state (current broken impl)
func (v Version) DebugDirtyInfo(ctx context.Context) (*DebugInfo, error) {
	checkout := v.Git.Head().Tree()
	changes := v.Inputs.Changes(checkout)

	isEmpty, err := changes.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	added, err := changes.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get added paths: %w", err)
	}

	modified, err := changes.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get modified paths: %w", err)
	}

	removed, err := changes.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get removed paths: %w", err)
	}

	inputsDigest, err := v.Inputs.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get inputs digest: %w", err)
	}

	checkoutDigest, err := checkout.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get checkout digest: %w", err)
	}

	return &DebugInfo{
		IsDirty:        !isEmpty,
		AddedPaths:     added,
		ModifiedPaths:  modified,
		RemovedPaths:   removed,
		InputsDigest:   inputsDigest,
		CheckoutDigest: checkoutDigest,
	}, nil
}

// DebugDirtyFixed returns info using the fixed approach: overlay inputs on checkout then compare
func (v Version) DebugDirtyFixed(ctx context.Context) (*DebugInfo, error) {
	checkout := v.Git.Head().Tree()
	combined := checkout.WithDirectory("", v.Inputs)
	changes := combined.Changes(checkout)

	isEmpty, err := changes.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	added, err := changes.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get added paths: %w", err)
	}

	modified, err := changes.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get modified paths: %w", err)
	}

	removed, err := changes.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get removed paths: %w", err)
	}

	combinedDigest, err := combined.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get combined digest: %w", err)
	}

	checkoutDigest, err := checkout.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get checkout digest: %w", err)
	}

	return &DebugInfo{
		IsDirty:        !isEmpty,
		AddedPaths:     added,
		ModifiedPaths:  modified,
		RemovedPaths:   removed,
		InputsDigest:   combinedDigest,
		CheckoutDigest: checkoutDigest,
	}, nil
}

// DebugDirtyGitStatus returns dirty state using git status (respects .gitignore)
func (v Version) DebugDirtyGitStatus(ctx context.Context) (*DebugGitStatusInfo, error) {
	checkout := v.Git.Head().Tree()
	combined := checkout.WithDirectory("", v.Inputs)
	status, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".", combined).
		WithExec([]string{"git", "status", "--porcelain"}).
		Stdout(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to run git status: %w", err)
	}
	status = strings.TrimSpace(status)
	var changedFiles []string
	if status != "" {
		changedFiles = strings.Split(status, "\n")
	}
	return &DebugGitStatusInfo{
		IsDirty:      status != "",
		GitStatus:    status,
		ChangedFiles: changedFiles,
	}, nil
}

type DebugGitStatusInfo struct {
	IsDirty      bool
	GitStatus    string
	ChangedFiles []string
}

type DebugInfo struct {
	IsDirty        bool
	AddedPaths     []string
	ModifiedPaths  []string
	RemovedPaths   []string
	InputsDigest   string
	CheckoutDigest string
}

// DebugGitUncommitted returns info using GitRepository.Uncommitted() API
func (v Version) DebugGitUncommitted(ctx context.Context) (*DebugUncommittedInfo, error) {
	uncommitted := v.Git.Uncommitted()

	isEmpty, err := uncommitted.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	added, err := uncommitted.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get added paths: %w", err)
	}

	modified, err := uncommitted.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get modified paths: %w", err)
	}

	removed, err := uncommitted.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get removed paths: %w", err)
	}

	return &DebugUncommittedInfo{
		IsEmpty:       isEmpty,
		AddedPaths:    added,
		ModifiedPaths: modified,
		RemovedPaths:  removed,
	}, nil
}

type DebugUncommittedInfo struct {
	IsEmpty       bool
	AddedPaths    []string
	ModifiedPaths []string
	RemovedPaths  []string
}

// DebugInputsEntries returns the first N entries from the inputs directory
func (v Version) DebugInputsEntries(ctx context.Context, limit int) ([]string, error) {
	entries, err := v.Inputs.Entries(ctx)
	if err != nil {
		return nil, err
	}
	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries, nil
}

// DebugCheckoutEntries returns the first N entries from the git HEAD checkout
func (v Version) DebugCheckoutEntries(ctx context.Context, limit int) ([]string, error) {
	checkout := v.Git.Head().Tree()
	entries, err := checkout.Entries(ctx)
	if err != nil {
		return nil, err
	}
	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries, nil
}

// DebugCompareDirectories shows the difference between inputs and checkout at root level
func (v Version) DebugCompareDirectories(ctx context.Context) (*DebugDirectoryComparison, error) {
	checkout := v.Git.Head().Tree()

	inputsEntries, err := v.Inputs.Entries(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get inputs entries: %w", err)
	}

	checkoutEntries, err := checkout.Entries(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get checkout entries: %w", err)
	}

	inputsSet := make(map[string]bool)
	for _, e := range inputsEntries {
		inputsSet[e] = true
	}
	checkoutSet := make(map[string]bool)
	for _, e := range checkoutEntries {
		checkoutSet[e] = true
	}

	var onlyInInputs, onlyInCheckout, inBoth []string
	for _, e := range inputsEntries {
		if checkoutSet[e] {
			inBoth = append(inBoth, e)
		} else {
			onlyInInputs = append(onlyInInputs, e)
		}
	}
	for _, e := range checkoutEntries {
		if !inputsSet[e] {
			onlyInCheckout = append(onlyInCheckout, e)
		}
	}

	return &DebugDirectoryComparison{
		InputsCount:    len(inputsEntries),
		CheckoutCount:  len(checkoutEntries),
		OnlyInInputs:   onlyInInputs,
		OnlyInCheckout: onlyInCheckout,
		InBoth:         inBoth,
	}, nil
}

type DebugDirectoryComparison struct {
	InputsCount    int
	CheckoutCount  int
	OnlyInInputs   []string
	OnlyInCheckout []string
	InBoth         []string
}

// DebugDirtyUncommitted uses GitRepository.Uncommitted() with the full repo (staff engineer fix)
func (v Version) DebugDirtyUncommitted(
	ctx context.Context,
	// Full repo directory with worktree
	// +defaultPath="/"
	source *dagger.Directory,
) (*DebugGitStatusInfo, error) {
	gitRepo := source.AsGit()
	uncommitted := gitRepo.Uncommitted()

	isEmpty, err := uncommitted.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	var changedFiles []string
	if !isEmpty {
		added, _ := uncommitted.AddedPaths(ctx)
		modified, _ := uncommitted.ModifiedPaths(ctx)
		removed, _ := uncommitted.RemovedPaths(ctx)
		for _, p := range added {
			changedFiles = append(changedFiles, "A  "+p)
		}
		for _, p := range modified {
			changedFiles = append(changedFiles, "M  "+p)
		}
		for _, p := range removed {
			changedFiles = append(changedFiles, "D  "+p)
		}
	}

	return &DebugGitStatusInfo{
		IsDirty:      !isEmpty,
		GitStatus:    strings.Join(changedFiles, "\n"),
		ChangedFiles: changedFiles,
	}, nil
}
