package gitutil

import (
	"strconv"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestMergeGitConfigEnv_AppendsAfterMaxIndexOrCount(t *testing.T) {
	env := []string{
		"FOO=bar",
		"GIT_CONFIG_KEY_7=core.abbrev",
		"GIT_CONFIG_VALUE_7=12",
		"GIT_CONFIG_COUNT=3", // stale/small
		"GIT_CONFIG_COUNT=5", // duplicate, still < 7+1
		"OTHER=keepme",
	}
	add := map[string]string{
		"http.https://host/.extraheader": "Authorization: basic abc",
		"core.autocrlf":                  "false",
	}
	got := MergeGitConfigEnv(env, add)

	require.Contains(t, got, "FOO=bar")
	require.Contains(t, got, "OTHER=keepme")

	require.Contains(t, got, "GIT_CONFIG_KEY_8=http.https://host/.extraheader")
	require.Contains(t, got, "GIT_CONFIG_VALUE_8=Authorization: basic abc")
	require.Contains(t, got, "GIT_CONFIG_KEY_9=core.autocrlf")
	require.Contains(t, got, "GIT_CONFIG_VALUE_9=false")

	require.Equal(t, "GIT_CONFIG_COUNT=10", got[len(got)-1])
}

func TestMergeGitConfigEnv_DeterministicOrder(t *testing.T) {
	env := []string{}
	add := map[string]string{
		"b.key": "2",
		"a.key": "1",
	}
	got := MergeGitConfigEnv(env, add)
	idxA, idxB := -1, -1
	for _, e := range got {
		if strings.HasPrefix(e, "GIT_CONFIG_KEY_") && strings.HasSuffix(e, "=a.key") {
			idxA, _ = strconv.Atoi(strings.TrimPrefix(strings.SplitN(e, "=", 2)[0], "GIT_CONFIG_KEY_"))
		}
		if strings.HasPrefix(e, "GIT_CONFIG_KEY_") && strings.HasSuffix(e, "=b.key") {
			idxB, _ = strconv.Atoi(strings.TrimPrefix(strings.SplitN(e, "=", 2)[0], "GIT_CONFIG_KEY_"))
		}
	}
	require.NotEqual(t, -1, idxA)
	require.NotEqual(t, -1, idxB)
	require.Less(t, idxA, idxB, "keys must be appended in sorted order (a before b)")
}
