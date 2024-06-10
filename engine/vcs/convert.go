package vcs

import (
	"context"
	"fmt"
	"path"
	"regexp"
	"strings"

	"github.com/dagger/dagger/core"
	"github.com/moby/buildkit/util/gitutil"
	"github.com/moby/buildkit/util/sshutil"
)

// convertToBuildKitRef converts a Go/Git inspired ref to BuildKit compatible syntax across all SCM providers.
// In case of failure, the ref is returned as is, as it will fail at the gitdns.Git level
func ConvertToBuildKitRef(ctx context.Context, ref string, bk buildkitClient) (string, *core.ModuleSourceKind, error) {
	// Retro-compatibility with previous ref schema
	if strings.Contains(ref, "#") {
		// # represents version, only git kind has version
		return ref, &core.ModuleSourceKindGit, nil
	}

	// Explicit file path case
	if strings.HasPrefix(ref, "file://") {
		return ref, &core.ModuleSourceKindLocal, nil
	}

	// cut version from ref, for both implicit ssh transport and new refs
	// build a compatible ref for parseRefString
	var userRefParsed parsedRefString
	if sshutil.IsImplicitSSHTransport(ref) || strings.HasPrefix(ref, "ssh") {
		re := regexp.MustCompile(`^(ssh://)?([a-zA-Z0-9-_]+)@([a-zA-Z0-9-.]+)([:/])(.*?)(?:@([^@]+))?$`)
		matches := re.FindStringSubmatch(ref)
		if len(matches) > 0 {
			userRefParsed.ModPath = matches[1] + matches[2] + "@" + matches[3] + matches[4] + matches[5]
			userRefParsed.ModVersion = matches[6]
			userRefParsed.HasVersion = userRefParsed.ModVersion != ""
		} else {
			return ref, &core.ModuleSourceKindGit, fmt.Errorf("failed to parse the ssh transport git ref: %s", ref)
		}

	} else {
		fmt.Printf("✅ parsedURL.Path: |%s| - userRefParsed.modVersion: |%s|\n", ref, userRefParsed.ModVersion)
		// Handle regular case
		userRefParsed.ModPath, userRefParsed.ModVersion, userRefParsed.HasVersion = strings.Cut(ref, "@")
	}

	// extract a valid ref for the ParseRefString call
	parsedURL, err := resolveGitURL(userRefParsed.ModPath)
	if err != nil {
		// Do we fallback ???
		return ref, nil, fmt.Errorf("failed to parse ref %s as a git URL: %w", ref, err)
	}

	fmt.Printf("✅🥶  userRefParsed.modPath: |%s|\n", userRefParsed.ModPath)

	fullURLPath := path.Join(parsedURL.Host, parsedURL.Path)

	parsed := ParseRefString(ctx, bk, fullURLPath)
	isRemote := parsed.Kind == core.ModuleSourceKindGit

	if !isRemote {
		if userRefParsed.HasVersion {
			return ref, nil, fmt.Errorf("local ref %s should not have a version", ref)
		}

		return ref, &core.ModuleSourceKindLocal, nil
	}

	repoRoot, err := resolveGitURL(parsed.RepoRoot.Repo)
	if err != nil {
		return ref, nil, fmt.Errorf("failed to parse root of repo %s as a git URL: %w", parsed.RepoRoot.Repo, err)
	}

	return buildFinalURL(parsedURL, repoRoot, userRefParsed, userRefParsed.ModPath), &core.ModuleSourceKindGit, nil
}

// buildFinalURL constructs the final URL from the parsed components.
func buildFinalURL(userRef, repoRoot *gitutil.GitURL, refDetails parsedRefString, refWithoutVersion string) string {
	var sb strings.Builder

	sb.WriteString(userRef.Scheme)
	sb.WriteString("://")

	if userRef.User != nil {
		sb.WriteString(userRef.User.String())
		sb.WriteString("@")
	}

	sb.WriteString(repoRoot.Host)

	if sshutil.IsImplicitSSHTransport(refWithoutVersion) {
		sb.WriteString(":")
	} else {
		sb.WriteString("/")
	}

	repoPath, subdir := splitPathAndSubdir(cleanPath(userRef.Path), cleanPath(repoRoot.Path))
	repoPath = normalizeGitSuffix(refWithoutVersion, repoPath)

	sb.WriteString(repoPath)

	if refDetails.HasVersion {
		sb.WriteString("#")
		sb.WriteString(refDetails.ModVersion)
	}

	if len(subdir) > 0 {
		sb.WriteString(":")
		sb.WriteString(subdir)
	}

	return sb.String()
}

// resolve the ref as a Git URL
func resolveGitURL(ref string) (*gitutil.GitURL, error) {
	u, err := gitutil.ParseURL(ref)
	if err != nil {
		if err == gitutil.ErrUnknownProtocol {
			u, err = gitutil.ParseURL("https://" + ref)
		}
		if err != nil {
			return nil, fmt.Errorf("failed to parse URL: %w", err)
		}
	}
	return u, nil
}

// extract path to root of repo and subdir
func splitPathAndSubdir(refPath, rootPath string) (string, string) {
	// Vanity URL case
	if !strings.HasPrefix(refPath, rootPath) {
		return extractSubdirVanityURL(rootPath, refPath)
	}

	subdir := strings.TrimPrefix(refPath, rootPath)
	subdir = strings.TrimPrefix(subdir, "/")

	return rootPath, subdir
}

// normalizes ".git" suffix according to user ref
func normalizeGitSuffix(ref, root string) string {
	refContainsGit := strings.Contains(ref, ".git")

	if refContainsGit {
		return root + ".git"
	}
	return root
}

// cleanPath removes leading slashes and ".git" from the path.
func cleanPath(p string) string {
	return strings.TrimPrefix(strings.ReplaceAll(p, ".git", ""), "/")
}

// extract root and subdir for vanity URLs when one element of the root URL path is a prefix of the module path
// Problem solved: vanity URLs generally do not have the same root URL structure as the userRefPath
// We then need to find a heuristic to isolate, from the vanity URL, the root and the path
func extractSubdirVanityURL(rootURLPath, userRefPath string) (string, string) {
	rootComponents := strings.Split(strings.Trim(rootURLPath, "/"), "/")
	modulePathComponents := strings.Split(strings.Trim(userRefPath, "/"), "/")

	modIndexMap := make(map[string]int)
	for i, component := range modulePathComponents {
		modIndexMap[component] = i
	}

	// Iterate over the root components in reverse order to find the deepest match first,
	// ensuring we get the most specific subdirectory.
	for i := len(rootComponents) - 1; i >= 0; i-- {
		if j, found := modIndexMap[rootComponents[i]]; found {
			subdir := strings.Join(modulePathComponents[j+1:], "/")
			return rootURLPath, subdir
		}
	}

	return strings.TrimSuffix(rootURLPath, "/"), ""
}
