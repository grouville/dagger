package core

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/dagger/dagger/core/workspace"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

// Exercise the real session-owned clone/delta and graceful-shutdown export,
// rather than a resolver mock that shares a mutable lock across calls. The
// existing small public Git fixture has a pinned commit and declares source
// "dagger". Reading its metadata does not execute its Go module or download an SDK.
func (LockfileSuite) TestVanityIdentityPersistsAcrossSessions(ctx context.Context, t *testctx.T) {
	const repoURL = "https://github.com/dagger/dagger-test-modules"
	workdir := t.TempDir()
	hostGitInit(t, workdir)
	writeEmptyWorkspaceConfig(t, workdir)
	lockPath := filepath.Join(workdir, workspace.LockFileName)
	require.NoFileExists(t, lockPath)

	queryPath := writeQueryDoc(t, workdir, "identity.graphql", fmt.Sprintf(`{
	  moduleSource(refString: %q, allowNotExists: true, disableFindUp: true) {
	    commit
	    sourceSubpath
	  }
	}`, repoURL+"#"+vcsTestCaseCommit))
	run := func() {
		t.Helper()
		out, err := hostDaggerExecRaw(ctx, t, workdir, "--silent", "api", "query", "--no-load-module", "--doc", queryPath)
		require.NoError(t, err, string(out))
		require.JSONEq(t, fmt.Sprintf(`{"moduleSource":{"commit":%q,"sourceSubpath":"dagger"}}`, vcsTestCaseCommit), string(out))
	}
	readLock := func() ([]byte, *workspace.Lock) {
		t.Helper()
		data, err := os.ReadFile(lockPath)
		require.NoError(t, err, "the completed CLI must export its session delta")
		lock, err := workspace.ParseLock(data)
		require.NoError(t, err)
		value, ok := lock.GetLookup(workspace.CoreLockNamespace, workspace.LockOperationVanityURLResolution, []any{repoURL})
		require.True(t, ok, "the identity must be discovered through the ordinary source resolver")
		require.Equal(t, repoURL, value)
		return data, lock
	}

	run()
	_, lock := readLock()
	// Unrelated unknown entries must survive subsequent reads and updates too.
	require.NoError(t, lock.SetLookup("test", "preserve", []any{"other-input"}, "other-value"))
	expected, err := lock.Marshal()
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(lockPath, expected, 0o600))

	// A separate process/session reads the file exported by the first one.
	run()
	after, _ := readLock()
	require.Equal(t, expected, after)

	out, err := hostDaggerExecRaw(ctx, t, workdir, "workspace", "update")
	require.NoError(t, err, string(out))
	after, _ = readLock()
	require.Equal(t, expected, after, "refreshing an unchanged HTTP 200 preserves both entries")
}
