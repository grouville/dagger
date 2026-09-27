package daggercmd

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"

	"dagger.io/dagger"
	"github.com/Khan/genqlient/graphql"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/gqlerror"
)

func TestCLITypeDefsJSONCapabilityErrors(t *testing.T) {
	missing := &gqlerror.Error{Message: `Cannot query field "__currentTypeDefsJSON" on type "Query".`}
	for _, tc := range []struct {
		name string
		err  error
		want bool
	}{
		{"supported", nil, false},
		{"missing", missing, true},
		{"wrapped", fmt.Errorf("wrapped: %w", missing), true},
		{"single list", gqlerror.List{missing}, true},
		{"multiple errors", gqlerror.List{missing, &gqlerror.Error{Message: "forbidden"}}, false},
		{"http validation", &graphql.HTTPError{StatusCode: 422, Response: graphql.Response{Errors: gqlerror.List{missing}}}, true},
		{"http unauthorized", &graphql.HTTPError{StatusCode: 401, Response: graphql.Response{Errors: gqlerror.List{missing}}}, false},
		{"resolver path", &gqlerror.Error{Message: missing.Message, Path: ast.Path{ast.PathName("typeDefs")}}, false},
		{"other field", &gqlerror.Error{Message: `Cannot query field "other" on type "Query".`}, false},
		{"plain string", errors.New(missing.Message), false},
	} {
		t.Run(tc.name, func(t *testing.T) { require.Equal(t, tc.want, missingCLITypeDefsJSON(tc.err)) })
	}
}

func TestCLITypeDefsJSONTransportFallback(t *testing.T) {
	const metadata = `[{"name":"Query","kind":"OBJECT_KIND","optional":false,"asObject":{"name":"Query","description":"Root","sourceModuleName":"","constructor":null,"functions":[],"fields":[]}}]`
	for _, tc := range []struct {
		name    string
		first   any
		code    int
		calls   int
		wantErr string
	}{
		{"supported", map[string]any{"data": map[string]any{"typeDefs": metadata}}, 200, 1, ""},
		{"old engine", map[string]any{"errors": []any{map[string]any{"message": `Cannot query field "__currentTypeDefsJSON" on type "Query".`, "locations": []any{map[string]any{"line": 2, "column": 4}}}}}, 200, 2, ""},
		{"old engine validation status", map[string]any{"errors": []any{map[string]any{"message": `Cannot query field "__currentTypeDefsJSON" on type "Query".`}}}, 422, 2, ""},
		{"resolver error", map[string]any{"errors": []any{map[string]any{"message": "permission denied", "path": []string{"typeDefs"}}}}, 200, 1, "permission denied"},
		{"invalid JSON", map[string]any{"data": map[string]any{"typeDefs": "not JSON"}}, 200, 1, "decode module objects"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			dag, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
				calls++
				var query dagger.Request
				require.NoError(t, json.NewDecoder(req.Body).Decode(&query))
				require.Equal(t, true, query.Variables.(map[string]any)["hideCore"])
				var response any = tc.first
				status := tc.code
				if calls == 1 {
					require.Contains(t, query.Query, "__currentTypeDefsJSON")
				} else {
					require.NotContains(t, query.Query, "__currentTypeDefsJSON")
					require.True(t, strings.Contains(query.Query, "currentTypeDefs(returnAllTypes"))
					response = map[string]any{"data": map[string]any{"typeDefs": json.RawMessage(metadata)}}
					status = 200
				}
				raw, err := json.Marshal(response)
				require.NoError(t, err)
				return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(bytes.NewReader(raw))}, nil
			}}))
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, dag.Close()) })
			var mod moduleDef
			err = mod.loadTypeDefs(t.Context(), dag, loadTypeDefsOpts{HideCore: true})
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
			} else {
				require.NoError(t, err)
				require.NotNil(t, mod.GetTypeDef("Query"))
			}
			require.Equal(t, tc.calls, calls)
		})
	}
}
