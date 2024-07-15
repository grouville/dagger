package schema

import (
	"context"
	"os"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/engine/vcs"
	"github.com/stretchr/testify/require"
	"github.com/tonistiigi/fsutil/types"
)

// Test ParseRefString using an interface to control Host side effect
func TestParseRefString(t *testing.T) {
	ctx := context.Background()

	bkClientDirFalse := &MockBuildkitClient{
		StatFunc: func(ctx context.Context, path string, followLinks bool) (*types.Stat, error) {
			return &types.Stat{Mode: uint32(os.ModeDevice)}, nil // stat.Dir() returns false
		},
	}

	for _, tc := range []struct {
		urlStr     string
		mockClient buildkitClient
		want       *parsedRefString
	}{
		// github
		{
			urlStr: "github.com/shykes/daggerverse/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "github.com/shykes/daggerverse.git/../../",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/../../",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "../../",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "git+https://github.com/shykes/daggerverse/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitHTTPS,
				sshusername:    "",
			},
		},
		{
			urlStr: "git+http://github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitHTTP,
				sshusername:    "",
			},
		},
		{
			urlStr: "git+ssh://github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitSSH,
				sshusername:    "",
			},
		},
		{
			urlStr: "git+ssh://github.com/shykes/daggerverse/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitSSH,
				sshusername:    "",
			},
		},
		{
			urlStr: "ssh://github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeSSH,
				sshusername:    "",
			},
		},
		{
			urlStr: "ssh://git@github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse.git", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeSSH,
				sshusername:    "git",
			},
		},
		{
			urlStr: "git+ssh://user@github.com/shykes/daggerverse/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitSSH,
				sshusername:    "user",
			},
		},
		{
			urlStr: "ssh://github.com/shykes/daggerverse/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeSSH,
				sshusername:    "",
			},
		},
		{
			urlStr: "git+ssh://user@github.com/shykes/daggerverse/ci@version",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitSSH,
				sshusername:    "user",
				modVersion:     "version",
			},
		},
		{
			urlStr: "git+ssh://github.com/shykes/daggerverse/ci@version",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse/ci",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "github.com/shykes/daggerverse", Repo: "https://github.com/shykes/daggerverse"},
				repoRootSubdir: "ci",
				scheme:         core.SchemeGitSSH,
				sshusername:    "",
				modVersion:     "version",
			},
		},

		// GitLab
		{
			urlStr: "gitlab.com/testguigui1/dagger-public-sub/mywork/depth1/depth2",
			want: &parsedRefString{
				modPath:        "gitlab.com/testguigui1/dagger-public-sub/mywork/depth1/depth2",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "gitlab.com/testguigui1/dagger-public-sub/mywork", Repo: "https://gitlab.com/testguigui1/dagger-public-sub/mywork"},
				repoRootSubdir: "depth1/depth2",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "gitlab.com/testguigui1/dagger-public-sub/mywork.git/depth1/depth2",
			want: &parsedRefString{
				modPath:        "gitlab.com/testguigui1/dagger-public-sub/mywork.git/depth1/depth2",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "gitlab.com/testguigui1/dagger-public-sub/mywork.git", Repo: "https://gitlab.com/testguigui1/dagger-public-sub/mywork"},
				repoRootSubdir: "depth1/depth2",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},

		// Edge case of RepoRootForImportPath
		// private GitLab: go-get unauthenticated returns obfuscated repo root
		// https://gitlab.com/gitlab-org/gitlab-foss/-/blob/master/lib/gitlab/middleware/go.rb#L210-221
		{
			urlStr: "ssh://gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private/depth1/depth2",
			want: &parsedRefString{
				modPath:        "gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private/depth1/depth2",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "gitlab.com/dagger-modules/private", Repo: "https://gitlab.com/dagger-modules/private"},
				repoRootSubdir: "test/more/dagger-test-modules-private/depth1/depth2",
				scheme:         core.SchemeSSH,
				sshusername:    "",
			},
		},
		// private GitLab with ref including .git: here we declaratively know where the separation between repo and subdir is
		{
			urlStr: "ssh://gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private.git/depth1/depth2",
			want: &parsedRefString{
				modPath:        "gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private.git/depth1/depth2",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private.git", Repo: "https://gitlab.com/dagger-modules/private/test/more/dagger-test-modules-private"},
				repoRootSubdir: "depth1/depth2",
				scheme:         core.SchemeSSH,
				sshusername:    "",
			},
		},
		// bitbucket
		{
			urlStr: "bitbucket.org/test-travail/test/depth1",
			want: &parsedRefString{
				modPath:        "bitbucket.org/test-travail/test/depth1",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "bitbucket.org/test-travail/test", Repo: "https://bitbucket.org/test-travail/test"},
				repoRootSubdir: "depth1",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "bitbucket.org/test-travail/test.git/depth1",
			want: &parsedRefString{
				modPath:        "bitbucket.org/test-travail/test.git/depth1",
				kind:           core.ModuleSourceKindGit,
				repoRoot:       &vcs.RepoRoot{Root: "bitbucket.org/test-travail/test.git", Repo: "https://bitbucket.org/test-travail/test"},
				repoRootSubdir: "depth1",
				scheme:         core.NoScheme,
				sshusername:    "",
			},
		},
		{
			urlStr: "git@github.com/shykes/daggerverse.git/ci",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRootSubdir: "ci",
				sshusername:    "git",
				scheme:         core.SchemeImplicitSSH,
			},
		},
		{
			urlStr: "git@github.com/shykes/daggerverse.git/ci@version",
			want: &parsedRefString{
				modPath:        "github.com/shykes/daggerverse.git/ci",
				kind:           core.ModuleSourceKindGit,
				repoRootSubdir: "ci",
				sshusername:    "git",
				scheme:         core.SchemeImplicitSSH,
			},
		},
		{
			urlStr: "git@github.com/shykes/daggerverse.git@version",
			want: &parsedRefString{
				modPath:     "github.com/shykes/daggerverse.git",
				kind:        core.ModuleSourceKindGit,
				sshusername: "git",
				scheme:      core.SchemeImplicitSSH,
			},
		},
	} {
		tc := tc
		t.Run(tc.urlStr, func(t *testing.T) {
			t.Parallel()
			parsed := parseRefString(ctx, bkClientDirFalse, tc.urlStr)
			require.NotNil(t, parsed)
			require.Equal(t, tc.want.modPath, parsed.modPath)
			require.Equal(t, tc.want.kind, parsed.kind)
			if tc.want.repoRoot != nil {
				require.Equal(t, tc.want.repoRoot.Repo, parsed.repoRoot.Repo)
				require.Equal(t, tc.want.repoRoot.Root, parsed.repoRoot.Root)
			}
			require.Equal(t, tc.want.repoRootSubdir, parsed.repoRootSubdir)
			require.Equal(t, tc.want.scheme, parsed.scheme)
			require.Equal(t, tc.want.sshusername, parsed.sshusername)
		})
	}
}

// Mock BuildKit StatCallerHostPath call
type MockBuildkitClient struct {
	StatFunc func(ctx context.Context, path string, followLinks bool) (*types.Stat, error)
}

func (m *MockBuildkitClient) StatCallerHostPath(ctx context.Context, path string, followLinks bool) (*types.Stat, error) {
	return m.StatFunc(ctx, path, followLinks)
}

func TestLexicalRelativePath(t *testing.T) {
	tests := []struct {
		name     string
		cwdPath  string
		modPath  string
		expected string
		wantErr  bool
	}{
		{
			name:     "Simple relative path",
			cwdPath:  "/home/user",
			modPath:  "/home/user/project",
			expected: "project",
		},
		{
			name:     "Parent directory",
			cwdPath:  "/home/user/project",
			modPath:  "/home/user",
			expected: "..",
		},
		{
			name:     "Same directory",
			cwdPath:  "/home/user",
			modPath:  "/home/user",
			expected: ".",
		},
		{
			name:     "Windows style paths",
			cwdPath:  `C:\Users\user`,
			modPath:  `C:\Users\user\project`,
			expected: "project",
		},
		{
			name:    "Windows different drives",
			cwdPath: `C:\Users\user`,
			modPath: `D:\Projects\myproject`,
			wantErr: true,
		},
		{
			name:     "Windows UNC paths",
			cwdPath:  `\\server\share\folder`,
			modPath:  `\\server\share\folder\project`,
			expected: "project",
		},
		{
			name:     "Mixed slashes",
			cwdPath:  `/home/user/folder`,
			modPath:  `/home/user/folder/subfolder\project`,
			expected: "subfolder/project",
		},
		{
			name:    "Invalid relative path",
			cwdPath: "/home/user",
			modPath: "C:/Windows",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := lexicalRelativePath(tt.cwdPath, tt.modPath)

			if tt.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
				require.Equal(t, tt.expected, result)
			}
		})
	}
}
