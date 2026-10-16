package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	sdk "dagger.io/dagger"
	"dagger.io/dagger/core"
	"github.com/Khan/genqlient/graphql"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
)

type dispatchClient struct {
	*core.Query
	client *sdk.Client
}

func (c *dispatchClient) GraphQLClient() graphql.Client { return c.client.GraphQLClient() }

var dag *dispatchClient
var invokeCall func([]byte, string, string, map[string][]byte) (any, error)

func setMarshalContext(context.Context) {}
func invoke(_ context.Context, parent []byte, parentName, name string, args map[string][]byte) (any, error) {
	return invokeCall(parent, parentName, name, args)
}

type connection struct{ *httptest.Server }

func (c connection) Host() string                               { return strings.TrimPrefix(c.URL, "http://") }
func (c connection) Close() error                               { return nil }
func (c connection) Do(r *http.Request) (*http.Response, error) { return c.Client().Do(r) }

func TestDispatch(t *testing.T) {
	for _, tc := range []struct {
		name            string
		args            map[string]string
		failure         bool
		metadataFailure bool
	}{
		{name: "no arguments"},
		{name: "JSON values", args: map[string]string{
			"text": `"a\\b\n\"é\""`, "zero": `0`, "false": `false`,
			"empty": `""`, "null": `null`, "list": `[0,false,"é"]`,
			"object": `{"directory":"id","nested":[null,{}]}`,
		}},
		{name: "function error", failure: true},
		{name: "metadata error", metadataFailure: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			parent := `{"prefix":"é","zero":0}`
			args := []map[string]any{}
			byID := map[string]any{}
			for name, value := range tc.args {
				arg := map[string]any{"id": name, "name": name, "value": value}
				args = append(args, arg)
				byID[name] = arg
			}
			call := map[string]any{"parentName": "Example", "name": "ExampleMethod", "parent": parent, "inputArgs": args}
			var metadataQueries atomic.Int32
			var returned atomic.Value
			var errorReturned atomic.Bool
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var request struct{ Query string }
				if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
					http.Error(w, err.Error(), 400)
					return
				}
				doc, err := parser.ParseQuery(&ast.Source{Input: request.Query})
				if err != nil {
					http.Error(w, err.Error(), 400)
					return
				}
				data := map[string]any{}
				for _, selection := range doc.Operations[0].SelectionSet {
					field := selection.(*ast.Field)
					switch field.Name {
					case "currentFunctionCall":
						metadata := true
						for _, sub := range field.SelectionSet {
							f := sub.(*ast.Field)
							if f.Name == "returnValue" {
								returned.Store(f.Arguments.ForName("value").Value.Raw)
								metadata = false
							}
							if f.Name == "returnError" {
								errorReturned.Store(true)
								metadata = false
							}
						}
						if metadata {
							metadataQueries.Add(1)
							if tc.metadataFailure {
								w.Header().Set("Content-Type", "application/json")
								json.NewEncoder(w).Encode(map[string]any{"errors": []map[string]string{{"message": "metadata sentinel"}}})
								return
							}
						}
						data[field.Alias] = call
					case "node":
						// Also serve the old per-argument requests, so the request
						// count is a regression check rather than a mock restriction.
						data[field.Alias] = byID[field.Arguments.ForName("id").Value.Raw]
						if data[field.Alias] != nil {
							metadataQueries.Add(1)
						}
					case "error":
						data[field.Alias] = map[string]any{"id": "error-id"}
					}
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(map[string]any{"data": data})
			}))
			defer server.Close()
			client, err := sdk.Connect(t.Context(), sdk.WithConn(connection{server}))
			require.NoError(t, err)
			defer client.Close()
			dag = &dispatchClient{Query: core.NewQuery(client), client: client}
			called := false
			sentinel := errors.New("function sentinel")
			invokeCall = func(gotParent []byte, gotParentName, gotName string, gotArgs map[string][]byte) (any, error) {
				called = true
				require.Equal(t, parent, string(gotParent))
				require.Equal(t, "Example", gotParentName)
				require.Equal(t, "ExampleMethod", gotName)
				require.Len(t, gotArgs, len(tc.args))
				for name, value := range tc.args {
					require.Equal(t, value, string(gotArgs[name]))
				}
				if tc.failure {
					return nil, sentinel
				}
				return "result", nil
			}
			err = dispatch(t.Context())
			if tc.metadataFailure {
				require.ErrorContains(t, err, "metadata sentinel")
				require.False(t, called)
				require.True(t, errorReturned.Load())
			} else if tc.failure {
				require.ErrorIs(t, err, sentinel)
				require.True(t, errorReturned.Load())
			} else {
				require.NoError(t, err)
				require.Equal(t, `"result"`, returned.Load())
			}
			require.Equal(t, !tc.metadataFailure, called)
			require.EqualValues(t, 1, metadataQueries.Load(), "metadata must be read in one request")
		})
	}
}
