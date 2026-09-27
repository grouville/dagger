package daggercmd

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"dagger.io/dagger"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
)

// Parse the actual request and put the scalar response under its selected object
// path. This supports both the historical ID/node round trip and a composed
// query, so the request-count assertions independently distinguish them.
func artifactProjectionData(t testing.TB, query, encoded string) map[string]any {
	t.Helper()
	doc, err := parser.ParseQuery(&ast.Source{Input: query})
	require.NoError(t, err)
	var object func(ast.SelectionSet) map[string]any
	object = func(set ast.SelectionSet) map[string]any {
		out := map[string]any{}
		for _, selection := range set {
			switch node := selection.(type) {
			case *ast.InlineFragment:
				for key, value := range object(node.SelectionSet) {
					out[key] = value
				}
			case *ast.Field:
				key := node.Alias
				if key == "" {
					key = node.Name
				}
				switch node.Name {
				case "id":
					out[key] = "selected-artifacts"
				case "__itemsJSON":
					out[key] = encoded
				default:
					out[key] = object(node.SelectionSet)
				}
			}
		}
		return out
	}
	return object(doc.Operations[0].SelectionSet)
}

func artifactProjectionResponse(t testing.TB, data any) *http.Response {
	t.Helper()
	body, err := json.Marshal(data)
	require.NoError(t, err)
	return &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(bytes.NewReader(body))}
}

func artifactProjectionFields(t testing.TB, query string) []*ast.Field {
	t.Helper()
	doc, err := parser.ParseQuery(&ast.Source{Input: query})
	require.NoError(t, err)
	var fields []*ast.Field
	var walk func(ast.SelectionSet)
	walk = func(set ast.SelectionSet) {
		for _, selection := range set {
			switch node := selection.(type) {
			case *ast.Field:
				fields = append(fields, node)
				walk(node.SelectionSet)
			case *ast.InlineFragment:
				walk(node.SelectionSet)
			}
		}
	}
	walk(doc.Operations[0].SelectionSet)
	return fields
}

func TestArtifactJSONProjectionSingleRequestAndOrder(t *testing.T) {
	want := []listedArtifact{
		{URI: "dag+check://go/modules/tests/run?go-module=.&go-test=TestZ", Description: "last first", DimensionKeys: []struct{ Dimension, Key string }{{"Go.modules", "."}, {"GoModule.tests", "TestZ"}}},
		{URI: "dag+check://go/modules/tests/run?go-module=.&go-test=TestA", Description: "first second", DimensionKeys: []struct{ Dimension, Key string }{{"Go.modules", "."}, {"GoModule.tests", "TestA"}}},
	}
	encoded, err := json.Marshal(want)
	require.NoError(t, err)
	for _, flow := range []string{"check", "list", "generate", "dimension", "empty-dimension"} {
		t.Run(flow, func(t *testing.T) {
			var queries []string
			dag, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
				var request dagger.Request
				require.NoError(t, json.NewDecoder(req.Body).Decode(&request))
				queries = append(queries, request.Query)
				return artifactProjectionResponse(t, map[string]any{"data": artifactProjectionData(t, request.Query, string(encoded))}), nil
			}}))
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, dag.Close()) })
			selection := dagger.Ref[*dagger.Workspace](dag, "workspace-owner").Artifacts(dagger.WorkspaceArtifactsOpts{Include: []string{"go/modules/**"}})
			switch flow {
			case "check":
				selection = selection.FilterCheckCommand()
			case "generate":
				selection = selection.FilterGenerateCommand()
			}
			selection = selection.FilterURI("dag://go/modules?go-module=.")
			var got []listedArtifact
			if strings.Contains(flow, "dimension") {
				dimension := "GoModule.tests\"\\with space"
				if flow == "empty-dimension" {
					dimension = ""
				}
				got, err = readListedDimensionItems(t.Context(), dag, selection, dimension, true)
			} else {
				got, err = readListedArtifacts(t.Context(), dag, selection, true, false)
			}
			require.NoError(t, err)
			require.Equal(t, want, got, "projection must preserve response order, descriptions and dimension keys")
			require.Len(t, queries, 1, "an intermediate artifact ID request is unnecessary")
			fields := artifactProjectionFields(t, queries[0])
			require.Equal(t, "node", fields[0].Name)
			owner, err := fields[0].Arguments.ForName("id").Value.Value(nil)
			require.NoError(t, err)
			require.Equal(t, "workspace-owner", owner)
			var names []string
			for _, field := range fields {
				names = append(names, field.Name)
			}
			require.Equal(t, "artifacts", names[1], "catalog remains an ancestor of expansion")
			require.Equal(t, "filterUri", names[len(names)-2])
			require.Equal(t, "__itemsJSON", names[len(names)-1])
			require.NotContains(t, names, "id")
			leaf := fields[len(fields)-1]
			absolute, err := leaf.Arguments.ForName("absolute").Value.Value(nil)
			require.NoError(t, err)
			require.Equal(t, true, absolute)
			typed, err := leaf.Arguments.ForName("typeAssertion").Value.Value(nil)
			require.NoError(t, err)
			require.Equal(t, strings.Contains(flow, "dimension"), typed)
			if strings.Contains(flow, "dimension") {
				arg := leaf.Arguments.ForName("dimension")
				require.NotNil(t, arg, "explicit empty dimension must not become omission")
				value, err := arg.Value.Value(nil)
				require.NoError(t, err)
				if flow == "empty-dimension" {
					require.Equal(t, "", value)
				} else {
					require.Equal(t, "GoModule.tests\"\\with space", value)
				}
			} else {
				require.Nil(t, leaf.Arguments.ForName("dimension"))
			}
			// Selecting a leaf must not mutate the receiver used by other readers.
			_, err = selection.ID(t.Context())
			require.NoError(t, err)
			require.Len(t, queries, 2)
			require.NotContains(t, queries[1], "__itemsJSON")
		})
	}
}

func TestArtifactJSONProjectionKeepsArgumentPrerequisites(t *testing.T) {
	var queries []string
	dag, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
		var request dagger.Request
		require.NoError(t, json.NewDecoder(req.Body).Decode(&request))
		queries = append(queries, request.Query)
		return artifactProjectionResponse(t, map[string]any{"data": artifactProjectionData(t, request.Query, "[]")}), nil
	}}))
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, dag.Close()) })
	ws := dagger.Ref[*dagger.Workspace](dag, "workspace-owner")
	selection := ws.Artifacts().WithArtifacts(ws.Artifacts(dagger.WorkspaceArtifactsOpts{Include: []string{"other/**"}}))
	_, err = readListedArtifacts(t.Context(), dag, selection, false, false)
	require.NoError(t, err)
	require.Len(t, queries, 2, "the other Artifacts argument still needs ID marshalling")
	require.Contains(t, queries[0], "other/**")
	require.NotContains(t, queries[0], "__itemsJSON")
	require.Contains(t, queries[1], "withArtifacts")
	require.Contains(t, queries[1], "__itemsJSON")
}

func TestArtifactJSONProjectionClientAffinity(t *testing.T) {
	ownerCalls, otherCalls := 0, 0
	owner, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
		ownerCalls++
		var request dagger.Request
		require.NoError(t, json.NewDecoder(req.Body).Decode(&request))
		return artifactProjectionResponse(t, map[string]any{"data": artifactProjectionData(t, request.Query, `[{"uri":"dag://owned"}]`)}), nil
	}}))
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, owner.Close()) })
	other, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
		otherCalls++
		return nil, errors.New("wrong session")
	}}))
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, other.Close()) })
	selection := dagger.Ref[*dagger.Artifacts](owner, "owned-artifacts")
	items, err := readListedArtifacts(t.Context(), other, selection, false, false)
	require.NoError(t, err)
	require.Equal(t, "dag://owned", items[0].URI)
	require.Equal(t, 1, ownerCalls)
	require.Zero(t, otherCalls, "projection stays on the original SDK selection's client")
}

func TestArtifactJSONProjectionErrorsAndCancellation(t *testing.T) {
	for _, failure := range []string{"catalog", "expansion", "invalid-json"} {
		t.Run(failure, func(t *testing.T) {
			calls := 0
			dag, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
				calls++
				var request dagger.Request
				require.NoError(t, json.NewDecoder(req.Body).Decode(&request))
				if failure == "invalid-json" {
					return artifactProjectionResponse(t, map[string]any{"data": artifactProjectionData(t, request.Query, "{")}), nil
				}
				return artifactProjectionResponse(t, map[string]any{"errors": []map[string]any{{"message": failure + " sentinel"}}}), nil
			}}))
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, dag.Close()) })
			items, err := readListedArtifacts(t.Context(), dag, dagger.Ref[*dagger.Workspace](dag, "ws").Artifacts(), false, false)
			require.Error(t, err)
			require.Nil(t, items)
			if failure != "invalid-json" {
				require.ErrorContains(t, err, failure+" sentinel")
			}
			require.Equal(t, 1, calls, "errors must not cause retries or a second ID/leaf request")
		})
	}
	t.Run("blocked request joins cancellation", func(t *testing.T) {
		ctx, cancel := context.WithCancel(t.Context())
		defer cancel()
		entered := make(chan struct{})
		var once sync.Once
		dag, err := dagger.Connect(ctx, dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
			once.Do(func() { close(entered) })
			<-req.Context().Done()
			return nil, req.Context().Err()
		}}))
		require.NoError(t, err)
		t.Cleanup(func() { require.NoError(t, dag.Close()) })
		done := make(chan error, 1)
		go func() {
			_, err := readListedArtifacts(ctx, dag, dagger.Ref[*dagger.Workspace](dag, "ws").Artifacts(), false, false)
			done <- err
		}()
		select {
		case <-entered:
		case <-time.After(5 * time.Second):
			t.Fatal("request did not start")
		}
		cancel()
		select {
		case err := <-done:
			require.ErrorIs(t, err, context.Canceled)
		case <-time.After(5 * time.Second):
			t.Fatal(fmt.Errorf("projection did not join canceled request"))
		}
	})
}
