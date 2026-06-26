package git

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestIsGitConfigKeyAllowed(t *testing.T) {
	nullChar := "\x00"
	testcases := []struct {
		gitconfig string
		expected  *GitConfig
	}{
		{
			gitconfig: `credential.helper
osxkeychain` + nullChar + `init.defaultbranch
main` + nullChar + `user.name
User Name` + nullChar + `user.email
user-name@gmail.com` + nullChar + `commit.gpgsign
true` + nullChar + `url.ssh://git@github.com/.insteadof
https://github.com/` + nullChar + `core.excludesfile
~/.config/git/.gitignore` + nullChar + `protocol.file.allow
always` + nullChar + `core.repositoryformatversion
0` + nullChar + `core.filemode
true` + nullChar + `core.bare
false` + nullChar + `core.logallrefupdates
true` + nullChar + `core.ignorecase
true` + nullChar + `core.precomposeunicode
true` + nullChar + `remote.origin.url
git@github.com:some-user/some-repo.git` + nullChar + `remote.origin.fetch
+refs/heads/*:refs/remotes/origin/*` + nullChar,
			expected: &GitConfig{
				Entries: []*GitConfigEntry{
					{
						Key:   "url.ssh://git@github.com/.insteadof",
						Value: "https://github.com/",
					},
				},
			},
		},
		{
			gitconfig: `url.insteadof
bar
baz` + nullChar + `credential.helper
osxkeychain` + nullChar + ``,
			expected: &GitConfig{
				Entries: []*GitConfigEntry{
					{
						Key:   "url.insteadof",
						Value: "bar\nbaz",
					},
				},
			},
		},
	}

	for _, tc := range testcases {
		t.Run(tc.gitconfig, func(t *testing.T) {
			parsed, err := parseGitConfigOutput([]byte(tc.gitconfig))
			require.Nil(t, err)
			require.Equal(t, tc.expected, parsed)
		})
	}
}

func TestReadCredentialRequest(t *testing.T) {
	req, err := ReadCredentialRequest(strings.NewReader("protocol=https\nhost=GitLab.COM\npath=org/repo.git\n\n"))

	require.NoError(t, err)
	require.Equal(t, &GitCredentialRequest{
		Protocol: "https",
		Host:     "gitlab.com",
		Path:     "org/repo.git",
	}, req)
}

func TestWriteCredential(t *testing.T) {
	var out strings.Builder

	err := WriteCredential(&out, &CredentialInfo{
		Username: "x-token-auth",
		Password: "secret",
	})

	require.NoError(t, err)
	require.Equal(t, "username=x-token-auth\npassword=secret\n\n", out.String())
}

// More tests are in ./core/integration/git_test.go
