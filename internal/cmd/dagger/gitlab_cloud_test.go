package daggercmd

import (
	"testing"
	"time"

	cloudapi "github.com/dagger/dagger/internal/cloud"
	"github.com/stretchr/testify/require"
)

func TestGitLabWorkspaceSourcesPreserveInstanceAndNestedNamespace(t *testing.T) {
	sources := []cloudapi.Source{
		{ID: "12", Name: "team", Provider: "github", Instance: "https://github.com"},
		{ID: "-12", Name: "team", Provider: "gitlab", Instance: "https://gitlab.com"},
		{ID: "-13", Name: "team/sub", Provider: "gitlab", Instance: "https://gitlab.com"},
		{ID: "-14", Name: "team/sub", Provider: "gitlab", Instance: "https://gitlab.example.com"},
	}
	for _, tc := range []struct{ remote, id string }{
		{"git@gitlab.com:team/sub/project.git", "-13"},
		{"https://gitlab.example.com/team/sub/project.git", "-14"},
		{"github.com/team/project", "12"},
		{"team/project", "12"},
	} {
		source, ok := workspaceSourceForRepo(sources, tc.remote)
		require.True(t, ok, tc.remote)
		require.Equal(t, tc.id, source.ID)
	}
	_, ok := workspaceSourceForRepo(sources, "gitlab.com/team-other/project")
	require.False(t, ok)
	repos := setWorkspaceAutocheckRepoSelected([]string{"github.com/team/project", "gitlab.example.com/team/sub/project"}, "gitlab.com/team/sub/project", true)
	require.Equal(t, []string{"github.com/team/project", "gitlab.com/team/sub/project", "gitlab.example.com/team/sub/project"}, repos)
	repos = setWorkspaceAutocheckRepoSelected(repos, "git@gitlab.com:team/sub/project.git", false)
	require.Equal(t, []string{"github.com/team/project", "gitlab.example.com/team/sub/project"}, repos)
}

func TestGitLabConnectionsDoNotImplyGitHubConnection(t *testing.T) {
	client := fakeCloudClient(t, `{"data":{"githubConnection":null}}`, `{"data":{"sources":[{"id":"-42","name":"team/sub","provider":"gitlab","instance":"https://gitlab.example.com","configUrl":"https://gitlab.example.com/team/sub"}]}}`)
	connected, _ := (&CloudCLI{}).githubConnected(t.Context(), client)
	require.False(t, connected)
}

func TestGitLabMergeRequestCheckRows(t *testing.T) {
	started := time.Now()
	rows := cloudCheckRows("test", []cloudapi.CheckCommit{{
		Repo: "https://gitlab.example.com/team/sub/project", CommitSHA: "abcdef123456", Timestamp: started,
		Events: []cloudapi.CheckEvent{{Provider: "gitlab"}},
		Refs:   []cloudapi.CheckCommitRef{{Typename: "CheckCommitPullRequestRef", Number: 7, URL: "https://gitlab.example.com/team/sub/project/-/merge_requests/7"}},
		Checks: []cloudapi.Check{{Name: "test", Status: "success", StartedAt: &started}},
	}})
	require.Len(t, rows, 1)
	require.Empty(t, rows[0].Dimensions["github-repo"])
	require.Empty(t, rows[0].Dimensions["github-pr"])
	require.Equal(t, "7", rows[0].Dimensions["gitlab-mr"])
	filtered := filterCloudCheckRows(rows, cloudCheckSelectorFlags{GitRepo: []string{"git@gitlab.example.com:team/sub/project.git"}, GitLabMR: []string{"7"}})
	require.Len(t, filtered, 1)
	kind, address := cloudCheckWorkspaceAddress(rows[0])
	require.Equal(t, "mr", kind)
	require.Equal(t, "gitlab.example.com/team/sub/project@refs/merge-requests/7/head", address)
	require.Equal(t, "7", cloudMergeRequestNumber("refs/merge-requests/7/head"))
	require.Empty(t, cloudMergeRequestNumber("refs/merge-requests/not-a-number/head"))
}

func TestGitLabOAuthRedirectSupportsAlternateCloud(t *testing.T) {
	previous := integrationRedirectURI
	integrationRedirectURI = ""
	t.Cleanup(func() { integrationRedirectURI = previous })
	t.Setenv("DAGGER_CLOUD_EXTERNAL_URL", "https://cloud-test.example.com/")
	require.Equal(t, "https://cloud-test.example.com/gitlab/callback", gitlabOAuthRedirect())
	integrationRedirectURI = "http://localhost:3000/gitlab/callback"
	require.Equal(t, integrationRedirectURI, gitlabOAuthRedirect())
}
