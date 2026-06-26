package sdk

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestGoPrivateCredentialPatterns(t *testing.T) {
	t.Parallel()

	// Entries are kept verbatim (they are go module path patterns); only blanks are
	// trimmed and duplicates dropped, across and within the merged values.
	got := goPrivateCredentialPatterns(
		"github.com/acme, github.com/acme ,*.example.com,github.com/acme/*",
		"gitlab.com/team/*, *.example.com",
	)
	require.Equal(t, "github.com/acme,*.example.com,github.com/acme/*,gitlab.com/team/*", got)
}

func TestGoPrivateCredentialPatternsHostOnly(t *testing.T) {
	t.Parallel()

	got := goPrivateCredentialPatterns("github.com")

	require.Equal(t, "github.com", got)
}

func TestEffectiveGoPrivateIncludesSystemEnv(t *testing.T) {
	t.Setenv(daggerEngineSystemEnvPrefix+"GOPRIVATE", "gitlab.com/team/*")

	got := effectiveGoPrivate("github.com/acme")

	require.Equal(t, "github.com/acme,gitlab.com/team/*", got)
}
