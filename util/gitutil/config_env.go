package gitutil

import (
	"maps"
	"slices"
	"strconv"
	"strings"
)

// MergeGitConfigEnv merges git config entries into env using
// GIT_CONFIG_COUNT/KEY_i/VALUE_i.
//
// It removes any existing GIT_CONFIG_COUNT entry, preserves other variables,
// appends new pairs in sorted key order for determinism, and writes exactly
// one final COUNT. This is a fast path that trusts the current COUNT value
// and appends after it.
func MergeGitConfigEnv(env []string, entries map[string]string) []string {
	if len(entries) == 0 {
		return env
	}

	const countPrefix = "GIT_CONFIG_COUNT="

	next := 0
	out := make([]string, 0, len(env)+len(entries)*2+1)
	for _, e := range env {
		if s, ok := strings.CutPrefix(e, countPrefix); ok {
			if n, err := strconv.Atoi(s); err == nil && n > next {
				next = n
			}
			continue
		}
		out = append(out, e)
	}

	keys := slices.Sorted(maps.Keys(entries))
	for i, k := range keys {
		v := entries[k]
		idx := next + i
		out = append(out,
			"GIT_CONFIG_KEY_"+strconv.Itoa(idx)+"="+k,
			"GIT_CONFIG_VALUE_"+strconv.Itoa(idx)+"="+v,
		)
	}

	out = append(out, countPrefix+strconv.Itoa(next+len(keys)))
	return out
}
