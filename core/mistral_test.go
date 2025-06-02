package core

import (
	"context"
	"os"
	"strings"
	"testing"

	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine/cache"
)

type MistralTestQuery struct{}

func (MistralTestQuery) Type() *ast.Type {
	return &ast.Type{
		NamedType: "Query",
		NonNull:   true,
	}
}

type mistralMockSecret struct {
	uri string
}

func (mistralMockSecret) Type() *ast.Type {
	return &ast.Type{
		NamedType: "Secret",
		NonNull:   true,
	}
}

// TestMistralAPICall tests making an actual API call to Mistral
// This test requires MISTRAL_API_KEY environment variable to be set
func TestMistralAPICall(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping Mistral API integration test in short mode")
	}

	apiKey := os.Getenv("MISTRAL_API_KEY")
	if apiKey == "" {
		t.Skip("MISTRAL_API_KEY not set, skipping Mistral API integration test")
	}

	ctx := context.Background()

	// Set up a mock server environment
	q := MistralTestQuery{}
	srv := dagql.NewServer(q, dagql.NewSessionCache(cache.NewCache[digest.Digest, dagql.Typed]()))

	vars := map[string]string{
		"file://.env":           "",
		"env://MISTRAL_API_KEY": apiKey,
	}

	dagql.Fields[MistralTestQuery]{
		dagql.Func("secret", func(ctx context.Context, self MistralTestQuery, args struct {
			URI string
		}) (mistralMockSecret, error) {
			return mistralMockSecret{uri: args.URI}, nil
		}),
	}.Install(srv)

	dagql.Fields[mistralMockSecret]{
		dagql.Func("plaintext", func(ctx context.Context, self mistralMockSecret, _ struct{}) (string, error) {
			if val, ok := vars[self.uri]; ok {
				return val, nil
			}
			return "", nil
		}),
	}.Install(srv)

	// Create router and test routing
	router, err := NewLLMRouter(ctx, srv)
	require.NoError(t, err)
	require.Equal(t, apiKey, router.MistralAPIKey)

	// Test routing to Mistral endpoint
	endpoint, err := router.Route("mistral-7b-instruct")
	require.NoError(t, err)
	require.Equal(t, Mistral, endpoint.Provider)
	require.Equal(t, apiKey, endpoint.Key)
	require.Equal(t, "mistral-7b-instruct", endpoint.Model)
	require.NotNil(t, endpoint.Client)

	// Test that the client was created as OpenAI-compatible client
	openAIClient, ok := endpoint.Client.(*OpenAIClient)
	require.True(t, ok, "Mistral client should be OpenAI-compatible")
	require.Equal(t, endpoint, openAIClient.endpoint)

	// Test making an actual API call
	t.Run("simple chat completion", func(t *testing.T) {
		messages := []ModelMessage{
			{
				Role:    "user",
				Content: "Say 'Hello, Mistral!' and nothing else.",
			},
		}

		response, err := endpoint.Client.SendQuery(ctx, messages, nil)
		if err != nil {
			// Check if this is an authentication error
			if strings.Contains(err.Error(), "401") || strings.Contains(err.Error(), "unauthorized") {
				t.Fatalf("Authentication failed - check MISTRAL_API_KEY: %v", err)
			}
			// Check if this is a rate limit or other API error
			if strings.Contains(err.Error(), "429") {
				t.Fatalf("Rate limit exceeded: %v", err)
			}
			if strings.Contains(err.Error(), "400") {
				t.Fatalf("Bad request - possible API compatibility issue: %v", err)
			}
			if strings.Contains(err.Error(), "404") {
				t.Fatalf("Model not found - possible model name issue: %v", err)
			}
			if strings.Contains(err.Error(), "503") || strings.Contains(err.Error(), "502") {
				t.Fatalf("Mistral API service unavailable: %v", err)
			}
			t.Fatalf("Unexpected error calling Mistral API: %v", err)
		}

		require.NotNil(t, response)
		assert.NotEmpty(t, response.Content, "Response should have content")
		assert.Contains(t, strings.ToLower(response.Content), "hello", "Response should contain 'hello'")
		assert.Greater(t, response.TokenUsage.TotalTokens, int64(0), "Should report token usage")

		t.Logf("Mistral API Response: %s", response.Content)
		t.Logf("Token Usage - Input: %d, Output: %d, Total: %d", 
			response.TokenUsage.InputTokens, 
			response.TokenUsage.OutputTokens, 
			response.TokenUsage.TotalTokens)
	})

	// Test with tool calls (if supported)
	t.Run("tool calling capability", func(t *testing.T) {
		// Simple tool that adds two numbers
		tools := []LLMTool{
			{
				Name:        "add_numbers",
				Description: "Add two numbers together",
				Schema: map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"a": map[string]interface{}{"type": "number", "description": "First number"},
						"b": map[string]interface{}{"type": "number", "description": "Second number"},
					},
					"required": []string{"a", "b"},
				},
			},
		}

		messages := []ModelMessage{
			{
				Role:    "user",
				Content: "Please add 5 and 3 using the add_numbers tool.",
			},
		}

		response, err := endpoint.Client.SendQuery(ctx, messages, tools)
		if err != nil {
			// Tool calling might not be supported by all Mistral models
			if strings.Contains(err.Error(), "not supported") || strings.Contains(err.Error(), "invalid") {
				t.Skipf("Tool calling not supported by this Mistral model: %v", err)
			}
			t.Fatalf("Error testing tool calling: %v", err)
		}

		require.NotNil(t, response)
		if len(response.ToolCalls) > 0 {
			t.Logf("Tool calls detected: %+v", response.ToolCalls)
			// Verify tool call structure
			toolCall := response.ToolCalls[0]
			assert.Equal(t, "add_numbers", toolCall.Function.Name)
			assert.NotEmpty(t, toolCall.ID)
		} else {
			t.Logf("No tool calls made - response: %s", response.Content)
		}
	})
}

// TestMistralErrorScenarios tests various error conditions
func TestMistralErrorScenarios(t *testing.T) {
	ctx := context.Background()

	t.Run("invalid API key", func(t *testing.T) {
		router := &LLMRouter{
			MistralAPIKey: "invalid-key",
		}

		endpoint, err := router.Route("mistral-7b-instruct")
		require.NoError(t, err)

		messages := []ModelMessage{
			{Role: "user", Content: "Hello"},
		}

		_, err = endpoint.Client.SendQuery(ctx, messages, nil)
		if err != nil {
			assert.Contains(t, err.Error(), "401", "Should get authentication error with invalid key")
			t.Logf("Expected authentication error: %v", err)
		} else {
			t.Fatal("Expected authentication error with invalid API key")
		}
	})

	t.Run("invalid model name", func(t *testing.T) {
		apiKey := os.Getenv("MISTRAL_API_KEY")
		if apiKey == "" {
			t.Skip("MISTRAL_API_KEY not set")
		}

		router := &LLMRouter{
			MistralAPIKey: apiKey,
		}

		endpoint, err := router.Route("mistral-nonexistent-model")
		require.NoError(t, err)

		messages := []ModelMessage{
			{Role: "user", Content: "Hello"},
		}

		_, err = endpoint.Client.SendQuery(ctx, messages, nil)
		if err != nil {
			// Should get model not found or bad request error
			assert.True(t, 
				strings.Contains(err.Error(), "404") || 
				strings.Contains(err.Error(), "400") ||
				strings.Contains(err.Error(), "model"),
				"Should get model-related error, got: %v", err)
			t.Logf("Expected model error: %v", err)
		} else {
			t.Fatal("Expected error with nonexistent model")
		}
	})

	t.Run("empty API key", func(t *testing.T) {
		router := &LLMRouter{
			MistralAPIKey: "",
		}

		endpoint, err := router.Route("mistral-7b-instruct")
		require.NoError(t, err)

		messages := []ModelMessage{
			{Role: "user", Content: "Hello"},
		}

		_, err = endpoint.Client.SendQuery(ctx, messages, nil)
		if err != nil {
			t.Logf("Expected error with empty API key: %v", err)
		} else {
			t.Fatal("Expected error with empty API key")
		}
	})
}

// TestMistralBaseURLOverride tests using a custom base URL
func TestMistralBaseURLOverride(t *testing.T) {
	router := &LLMRouter{
		MistralAPIKey:  "test-key",
		MistralBaseURL: "https://custom-mistral-endpoint.com/v1",
	}

	endpoint, err := router.Route("mistral-7b-instruct")
	require.NoError(t, err)
	assert.Equal(t, "https://custom-mistral-endpoint.com/v1", endpoint.BaseURL)

	openAIClient, ok := endpoint.Client.(*OpenAIClient)
	require.True(t, ok)
	assert.Equal(t, endpoint, openAIClient.endpoint)
}