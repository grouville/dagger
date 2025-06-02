package core

import (
	"context"
	"fmt"
	"testing"

	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/assert"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine/cache"
)

type LLMTestQuery struct{}

func (LLMTestQuery) Type() *ast.Type {
	return &ast.Type{
		NamedType: "Query",
		NonNull:   true,
	}
}

type mockSecret struct {
	uri string
}

func (mockSecret) Type() *ast.Type {
	return &ast.Type{
		NamedType: "Secret",
		NonNull:   true,
	}
}

func TestLlmConfig(t *testing.T) {
	q := LLMTestQuery{}

	srv := dagql.NewServer(q, dagql.NewSessionCache(cache.NewCache[digest.Digest, dagql.Typed]()))

	vars := map[string]string{
		"file://.env":                    "",
		"env://ANTHROPIC_API_KEY":        "anthropic-api-key",
		"env://ANTHROPIC_BASE_URL":       "anthropic-base-url",
		"env://ANTHROPIC_MODEL":          "anthropic-model",
		"env://OPENAI_API_KEY":           "openai-api-key",
		"env://OPENAI_AZURE_VERSION":     "openai-azure-version",
		"env://OPENAI_BASE_URL":          "openai-base-url",
		"env://OPENAI_MODEL":             "openai-model",
		"env://OPENAI_DISABLE_STREAMING": "t",
		"env://GEMINI_API_KEY":           "gemini-api-key",
		"env://GEMINI_BASE_URL":          "gemini-base-url",
		"env://GEMINI_MODEL":             "gemini-model",
		"env://MISTRAL_API_KEY":          "mistral-api-key",
		"env://MISTRAL_BASE_URL":         "mistral-base-url",
		"env://MISTRAL_MODEL":            "mistral-model",
	}

	dagql.Fields[LLMTestQuery]{
		dagql.Func("secret", func(ctx context.Context, self LLMTestQuery, args struct {
			URI string
		}) (mockSecret, error) {
			if _, ok := vars[args.URI]; !ok {
				t.Fatalf("uri not found: %s", args.URI)
			}
			return mockSecret{uri: args.URI}, nil
		}),
	}.Install(srv)

	dagql.Fields[mockSecret]{
		dagql.Func("plaintext", func(ctx context.Context, self mockSecret, _ struct{}) (string, error) {
			return vars[self.uri], nil
		}),
	}.Install(srv)

	ctx := context.Background()
	r, err := NewLLMRouter(ctx, srv)
	assert.NoError(t, err)
	assert.Equal(t, "anthropic-api-key", r.AnthropicAPIKey)
	assert.Equal(t, "anthropic-base-url", r.AnthropicBaseURL)
	assert.Equal(t, "anthropic-model", r.AnthropicModel)
	assert.Equal(t, "openai-api-key", r.OpenAIAPIKey)
	assert.Equal(t, "openai-azure-version", r.OpenAIAzureVersion)
	assert.Equal(t, "openai-base-url", r.OpenAIBaseURL)
	assert.Equal(t, "openai-model", r.OpenAIModel)
	assert.True(t, r.OpenAIDisableStreaming)
	assert.Equal(t, "gemini-api-key", r.GeminiAPIKey)
	assert.Equal(t, "gemini-base-url", r.GeminiBaseURL)
	assert.Equal(t, "gemini-model", r.GeminiModel)
	assert.Equal(t, "mistral-api-key", r.MistralAPIKey)
	assert.Equal(t, "mistral-base-url", r.MistralBaseURL)
	assert.Equal(t, "mistral-model", r.MistralModel)
}

func TestMistralLLMIntegration(t *testing.T) {
	ctx := context.Background()

	// Test case 1: Router configuration for Mistral
	t.Run("router configuration", func(t *testing.T) {
		router := &LLMRouter{
			MistralAPIKey:  "test-mistral-key",
			MistralBaseURL: "https://api.mistral.ai/v1",
			MistralModel:   "mistral-large",
		}

		// Test model recognition
		assert.True(t, router.isMistralModel("mistral-7b-instruct"))
		assert.True(t, router.isMistralModel("mistral-large"))
		assert.True(t, router.isMistralModel("mistral/codestral"))
		assert.False(t, router.isMistralModel("gpt-4"))
		assert.False(t, router.isMistralModel("claude-3"))

		// Test routing
		endpoint, err := router.Route("mistral-7b-instruct")
		assert.NoError(t, err)
		assert.Equal(t, Mistral, endpoint.Provider)
		assert.Equal(t, "test-mistral-key", endpoint.Key)
		assert.Equal(t, "https://api.mistral.ai/v1", endpoint.BaseURL)
		assert.Equal(t, "mistral-7b-instruct", endpoint.Model)
		assert.NotNil(t, endpoint.Client)
	})

	// Test case 2: Test model alias resolution
	t.Run("model alias resolution", func(t *testing.T) {
		assert.Equal(t, "mistral-7b-instruct", resolveModelAlias("mistral"))
		assert.Equal(t, "mistral-large", resolveModelAlias("mistral-large"))
	})

	// Test case 3: Test default model selection with Mistral
	t.Run("default model selection", func(t *testing.T) {
		router := &LLMRouter{
			MistralAPIKey: "test-key",
		}
		assert.Equal(t, "mistral-7b-instruct", router.DefaultModel())

		// Test priority - OpenAI should take precedence
		router.OpenAIAPIKey = "openai-key"
		assert.Equal(t, "gpt-4.1", router.DefaultModel())
	})

	// Test case 4: Test actual client creation (this tests the OpenAI client wrapper)
	t.Run("client creation", func(t *testing.T) {
		endpoint := &LLMEndpoint{
			BaseURL:  "https://api.mistral.ai/v1",
			Key:      "test-key",
			Provider: Mistral,
			Model:    "mistral-7b-instruct",
		}

		client := newOpenAIClient(endpoint, "", false)
		assert.NotNil(t, client)
		assert.Equal(t, endpoint, client.endpoint)
		assert.False(t, client.disableStreaming)

		// Test error handling for missing API key
		assert.False(t, client.IsRetryable(fmt.Errorf("authentication failed")))
	})

	// Test case 5: Test environment variable loading
	t.Run("environment variables", func(t *testing.T) {
		q := LLMTestQuery{}
		srv := dagql.NewServer(q, dagql.NewSessionCache(cache.NewCache[digest.Digest, dagql.Typed]()))

		vars := map[string]string{
			"file://.env":               "",
			"env://MISTRAL_API_KEY":     "env-mistral-key",
			"env://MISTRAL_BASE_URL":    "https://custom-mistral.api.com",
			"env://MISTRAL_MODEL":       "mistral-custom",
		}

		dagql.Fields[LLMTestQuery]{
			dagql.Func("secret", func(ctx context.Context, self LLMTestQuery, args struct {
				URI string
			}) (mockSecret, error) {
				return mockSecret{uri: args.URI}, nil
			}),
		}.Install(srv)

		dagql.Fields[mockSecret]{
			dagql.Func("plaintext", func(ctx context.Context, self mockSecret, _ struct{}) (string, error) {
				if val, ok := vars[self.uri]; ok {
					return val, nil
				}
				return "", nil
			}),
		}.Install(srv)

		router, err := NewLLMRouter(ctx, srv)
		assert.NoError(t, err)
		assert.Equal(t, "env-mistral-key", router.MistralAPIKey)
		assert.Equal(t, "https://custom-mistral.api.com", router.MistralBaseURL)
		assert.Equal(t, "mistral-custom", router.MistralModel)
	})
}

func TestLlmConfigDisableStreaming(t *testing.T) {
	for _, tc := range []struct {
		name     string
		envFile  string
		expected bool
	}{
		{
			"not disabled by default",
			"",
			false,
		},
		{
			"explicitly not disabled, FALSE",
			"OPENAI_DISABLE_STREAMING=FALSE",
			false,
		},
		{
			"explicitly not disabled, 0",
			"OPENAI_DISABLE_STREAMING=0",
			false,
		},
		{
			"disabled, true",
			"OPENAI_DISABLE_STREAMING=true",
			true,
		},
		{
			"disabled, 1",
			"OPENAI_DISABLE_STREAMING=1",
			true,
		},
		{
			"empty value",
			"OPENAI_DISABLE_STREAMING=",
			false,
		},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			q := LLMTestQuery{}

			srv := dagql.NewServer(q, dagql.NewSessionCache(cache.NewCache[digest.Digest, dagql.Typed]()))
			dagql.Fields[LLMTestQuery]{
				dagql.Func("secret", func(ctx context.Context, self LLMTestQuery, args struct {
					URI string
				}) (mockSecret, error) {
					return mockSecret{uri: args.URI}, nil
				}),
			}.Install(srv)

			dagql.Fields[mockSecret]{
				dagql.Func("plaintext", func(ctx context.Context, self mockSecret, _ struct{}) (string, error) {
					if self.uri == "file://.env" {
						return tc.envFile, nil
					}
					return "", nil
				}),
			}.Install(srv)

			ctx := context.Background()
			r, err := NewLLMRouter(ctx, srv)
			assert.NoError(t, err)
			assert.Equal(t, tc.expected, r.OpenAIDisableStreaming)
		})
	}
}

func TestLlmConfigEnvFile(t *testing.T) {
	q := LLMTestQuery{}

	srv := dagql.NewServer(q, dagql.NewSessionCache(cache.NewCache[digest.Digest, dagql.Typed]()))
	dagql.Fields[LLMTestQuery]{
		dagql.Func("secret", func(ctx context.Context, self LLMTestQuery, args struct {
			URI string
		}) (mockSecret, error) {
			return mockSecret{uri: args.URI}, nil
		}),
	}.Install(srv)

	dagql.Fields[mockSecret]{
		dagql.Func("plaintext", func(ctx context.Context, self mockSecret, _ struct{}) (string, error) {
			if self.uri == "file://.env" {
				return `ANTHRIOPIC_API_KEY=anthropic-api-key
ANTHROPIC_BASE_URL=anthropic-base-url
ANTHROPIC_MODEL=anthropic-model
ANTHROPIC_API_KEY=anthropic-api-key
OPENAI_API_KEY=openai-api-key
OPENAI_AZURE_VERSION=openai-azure-version
OPENAI_BASE_URL=openai-base-url
OPENAI_MODEL=openai-model
OPENAI_DISABLE_STREAMING=TRUE
GEMINI_API_KEY=gemini-api-key
GEMINI_BASE_URL=gemini-base-url
GEMINI_MODEL=gemini-model
MISTRAL_API_KEY=mistral-api-key
MISTRAL_BASE_URL=mistral-base-url
MISTRAL_MODEL=mistral-model`, nil
			}
			return "", nil
		}),
	}.Install(srv)

	ctx := context.Background()
	r, err := NewLLMRouter(ctx, srv)
	assert.NoError(t, err)
	assert.Equal(t, "anthropic-api-key", r.AnthropicAPIKey)
	assert.Equal(t, "anthropic-base-url", r.AnthropicBaseURL)
	assert.Equal(t, "anthropic-model", r.AnthropicModel)
	assert.Equal(t, "openai-api-key", r.OpenAIAPIKey)
	assert.Equal(t, "openai-azure-version", r.OpenAIAzureVersion)
	assert.Equal(t, "openai-base-url", r.OpenAIBaseURL)
	assert.Equal(t, "openai-model", r.OpenAIModel)
	assert.True(t, r.OpenAIDisableStreaming)
	assert.Equal(t, "gemini-api-key", r.GeminiAPIKey)
	assert.Equal(t, "gemini-base-url", r.GeminiBaseURL)
	assert.Equal(t, "gemini-model", r.GeminiModel)
	assert.Equal(t, "mistral-api-key", r.MistralAPIKey)
	assert.Equal(t, "mistral-base-url", r.MistralBaseURL)
	assert.Equal(t, "mistral-model", r.MistralModel)
}

