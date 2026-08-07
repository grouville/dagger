package core

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLLMRouterNestedAPIKeyOverridesInheritedOAuth(t *testing.T) {
	ctx := context.Background()
	router := new(LLMRouter)
	load := func(values map[string]string) error {
		return router.LoadConfig(ctx, func(_ context.Context, key string) (string, error) {
			return values[key], nil
		})
	}

	require.NoError(t, load(map[string]string{
		"ANTHROPIC_AUTH_TOKEN": "outer-oauth-token",
	}))
	require.NoError(t, load(map[string]string{
		"ANTHROPIC_API_KEY": "nested-api-key",
	}))

	require.Equal(t, "nested-api-key", router.AnthropicAPIKey)
	require.Empty(t, router.AnthropicAuthToken,
		"a nested API key should replace, not coexist with, inherited OAuth auth")
	require.False(t, router.AnthropicIsOAuth)
}
