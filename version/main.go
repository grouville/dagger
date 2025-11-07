// Shared logic for managing Dagger versions
//
// In general, it attempts to follow go's psedudoversioning:
// https://go.dev/doc/modules/version-numbers
package main

import (
	"context"
	"errors"
	"fmt"
	"strconv"
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
) *Version {
	return &Version{
		Git:    git.AsGit(),
		GitDir: git,
		Inputs: inputs,
	}
}

type Version struct {
	// +private
	Git    *dagger.GitRepository
	GitDir *dagger.Directory

	// +private
	Inputs *dagger.Directory
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
		return fmt.Sprintf("%s-%s-dev-%s", next, pseudoversionTimestamp(time.Time{}), digest[:12]), nil
	}

	head := v.Git.Head()
	commit, err := head.Commit(ctx)
	if err != nil {
		return "", err
	}

	tag, err := v.currentTagForCommit(ctx, commit)
	if err != nil {
		return "", err
	}
	if tag != "" {
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
	commitDate, err := v.commitTimestamp(ctx, commit)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s-%s-dev-%s", next, pseudoversionTimestamp(commitDate), commit[:12]), nil
}

// Return the tag to use when auto-downloading the engine image from the CLI
func (v Version) ImageTag(ctx context.Context) (string, error) {
	if v.GitDir == nil {
		return "", nil
	}

	head := v.Git.Head()
	main := v.Git.Branch("main")

	dirty, err := v.Dirty(ctx)
	if err != nil {
		return "", err
	}
	if dirty {
		mergeBase, err := head.CommonAncestor(main).Commit(ctx)
		if err != nil {
			return "", err
		}
		return mergeBase, nil
	}

	if tag, err := v.CurrentTag(ctx); err != nil {
		return "", err
	} else if tag != "" {
		// this is a tagged release
		// (v<major>.<minor>.<patch>)
		return tag, nil
	}

	mergeBase, err := head.CommonAncestor(main).Commit(ctx)
	if err != nil {
		return "", err
	}
	return mergeBase, nil
}

func (v Version) Dirty(ctx context.Context) (bool, error) {
	if v.GitDir == nil || v.Inputs == nil {
		return false, nil
	}

	checkout := v.Git.Head().Tree()
	// XXX: doesn't handle removed files :(
	checkout = checkout.WithDirectory("", v.Inputs)
	status, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".", checkout).
		WithExec([]string{"git", "status", "--porcelain"}).
		Stdout(ctx)
	if err != nil {
		return false, err
	}
	status = strings.TrimSpace(status)
	return status != "", nil
}

func (v Version) CurrentTag(ctx context.Context) (string, error) {
	commit, err := v.Git.Head().Commit(ctx)
	if err != nil {
		return "", err
	}
	return v.currentTagForCommit(ctx, commit)
}

func (v Version) currentTagForCommit(ctx context.Context, commit string) (string, error) {
	if commit == "" {
		return "", nil
	}
	tags, err := v.versionTags(ctx, commit)
	if err != nil {
		return "", err
	}
	if len(tags) == 0 {
		return "", nil
	}
	return tags[len(tags)-1].Version, nil
}

func (v Version) LastReleaseVersion(ctx context.Context) (string, error) {
	tags, err := v.versionTags(ctx, "")
	if err != nil {
		return "", err
	}
	if len(tags) == 0 {
		return "", errNoReleases
	}
	return tags[len(tags)-1].Version, nil
}

func (v Version) NextReleaseVersion(ctx context.Context) (string, error) {
	nextVersion := ""

	content, err := v.nextVersionFile(ctx)
	if err != nil {
		return "", err
	}
	nextVersion = parseNextFile(content)

	lastVersion, err := v.LastReleaseVersion(ctx)
	if err != nil {
		if !errors.Is(err, errNoReleases) {
			return "", err
		}
	} else if lastVersion != "" {
		maybeNextVersion := bumpVersion(lastVersion)
		if semver.IsValid(nextVersion) {
			if semver.Compare(maybeNextVersion, nextVersion) > 0 {
				nextVersion = maybeNextVersion
			}
		} else {
			nextVersion = maybeNextVersion
		}
	}

	if nextVersion == "" {
		return "", fmt.Errorf("could not determine next version")
	}
	return nextVersion, nil
}

type versionTag struct {
	Tag     string
	Version string
	Date    string
	Commit  string
}

func (v Version) versionTags(ctx context.Context, commit string) ([]versionTag, error) {
	if v.GitDir == nil {
		return nil, nil
	}

	args := []string{
		"git", "tag",
		"-l", "v*",
		"--merged=HEAD",
		"--format", "%(refname:lstrip=2) %(objectname) %(creatordate:iso-strict)",
		"--sort", "version:refname",
	}
	if commit != "" {
		args = append(args, "--points-at", commit)
	}

	out, err := v.gitCommand(ctx, args...)
	if err != nil {
		return nil, err
	}
	out = strings.TrimSpace(out)
	if out == "" {
		return nil, nil
	}

	var tags []versionTag
	for _, line := range strings.Split(out, "\n") {
		fields := strings.Fields(line)
		if len(fields) != 3 {
			continue
		}
		tag := fields[0]
		commitSHA := fields[1]
		date := fields[2]
		version := tag
		if !semver.IsValid(version) {
			continue
		}
		tags = append(tags, versionTag{
			Tag:     tag,
			Version: version,
			Date:    date,
			Commit:  commitSHA,
		})
	}

	return tags, nil
}

func (v Version) commitTimestamp(ctx context.Context, commit string) (time.Time, error) {
	if commit == "" {
		return time.Time{}, fmt.Errorf("commit is required")
	}
	out, err := v.gitCommand(ctx, "git", "show", "-s", "--format=%cI", commit)
	if err != nil {
		return time.Time{}, err
	}
	out = strings.TrimSpace(out)
	if out == "" {
		return time.Time{}, fmt.Errorf("could not determine timestamp for commit %s", commit)
	}
	t, err := time.Parse(time.RFC3339, out)
	if err != nil {
		return time.Time{}, err
	}
	return t, nil
}

func (v Version) gitCommand(ctx context.Context, args ...string) (string, error) {
	if v.GitDir == nil {
		return "", nil
	}
	ctr := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".git", v.GitDir).
		WithEnvVariable("GIT_DIR", "/src/.git")
	return ctr.WithExec(args).Stdout(ctx)
}

var errNoReleases = errors.New("no releases found")

func (v Version) nextVersionFile(ctx context.Context) (string, error) {
	out, err := v.gitCommand(ctx, "git", "show", "HEAD:.changes/.next")
	if err != nil {
		var execErr *dagger.ExecError
		if errors.As(err, &execErr) {
			if strings.Contains(execErr.Stderr, "exists on disk, but not in") || strings.Contains(execErr.Stderr, "does not exist in") {
				return "", nil
			}
		}
		return "", err
	}
	return out, nil
}

func pseudoversionTimestamp(t time.Time) string {
	// go time formatting is bizarre - this translates to "yymmddhhmmss"
	return t.Format("060102150405")
}

func bumpVersion(version string) string {
	if !semver.IsValid(version) {
		return version
	}
	version = baseVersion(version)
	majorMinor := semver.MajorMinor(version)
	patchStr, _ := strings.CutPrefix(version, majorMinor+".")
	patch, _ := strconv.Atoi(patchStr)
	return fmt.Sprintf("%s.%d", majorMinor, patch+1)
}

func baseVersion(version string) string {
	version = strings.TrimSuffix(version, semver.Build(version))
	version = strings.TrimSuffix(version, semver.Prerelease(version))
	return version
}

func parseNextFile(content string) (version string) {
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		if strings.HasPrefix(line, "#") {
			continue
		}

		return baseVersion(line)
	}
	return ""
}
