package daggercmd

import (
	"net/url"
	"strings"
)

// normalizeRepository retains the instance and full namespace. Bare owner/repo
// addresses continue to mean GitHub for compatibility with existing commands.
func normalizeRepository(remote string) string {
	remote = strings.TrimSpace(remote)
	if strings.HasPrefix(remote, "git@") && !strings.Contains(remote, "://") {
		remote = "ssh://" + strings.Replace(remote, ":", "/", 1)
	}
	if strings.Contains(remote, "://") {
		if u, err := url.Parse(remote); err == nil {
			remote = strings.ToLower(u.Host) + "/" + strings.Trim(u.Path, "/")
		}
	}
	remote = strings.TrimSuffix(strings.TrimRight(remote, "/"), ".git")
	first, _, _ := strings.Cut(remote, "/")
	if strings.Count(remote, "/") == 1 && !strings.ContainsAny(first, ".:") {
		remote = "github.com/" + remote
	}
	if strings.HasPrefix(remote, "github.com") {
		return "github.com/" + normalizeGitHubRepo(remote)
	}
	return remote
}

func repositoryInstance(repository string) string {
	host, _, _ := strings.Cut(normalizeRepository(repository), "/")
	return "https://" + host
}
