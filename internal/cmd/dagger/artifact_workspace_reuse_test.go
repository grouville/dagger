package daggercmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"

	"dagger.io/dagger"
	"github.com/dagger/dagger/core/artifact"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/require"
)

func TestArtifactListReusesWorkspaceWithGlobalAliases(t *testing.T) {
	// Different SDKs can contribute colliding names. Even a path-filtered
	// listing must choose aliases that remain unambiguous in the full catalog.
	globalDimensions := artifact.Dimensions{
		{Identifier: "Go.modules", Name: "module", QualifiedName: "go-module"},
		{Identifier: "GoModule.tests", Name: "test", QualifiedName: "go-test"},
		{Identifier: "TypeScript.projects", Name: "module", QualifiedName: "ts-module"},
		{Identifier: "Dang.tests", Name: "test", QualifiedName: "dang-test"},
	}
	for _, tc := range []struct {
		name      string
		addresses []string
		path      string
		keys      []struct{ Dimension, Key string }
		flags     []string
	}{
		{
			name:  "unfiltered nested collections",
			path:  "go/modules/tests/run",
			keys:  []struct{ Dimension, Key string }{{"Go.modules", "."}, {"GoModule.tests", "TestAlpha"}},
			flags: []string{"--go-module=.", "--go-test=TestAlpha"},
		},
		{
			name:      "filtered TypeScript collection",
			addresses: []string{"ts/projects/check"}, path: "ts/projects/check",
			keys:  []struct{ Dimension, Key string }{{"TypeScript.projects", "web"}},
			flags: []string{"--ts-module=web"},
		},
		{
			name:      "filtered Dang collection",
			addresses: []string{"dang/tests/run"}, path: "dang/tests/run",
			keys:  []struct{ Dimension, Key string }{{"Dang.tests", "smoke"}},
			flags: []string{"--dang-test=smoke"},
		},
		{name: "no dimensions", addresses: []string{"lint"}, path: "lint"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			items, err := json.Marshal([]listedArtifact{{URI: "dag+check://" + tc.path, Description: "Run check", DimensionKeys: tc.keys}})
			require.NoError(t, err)
			workspaceReads, globalCatalogReads, dimensionReads := 0, 0, 0
			dag, err := dagger.Connect(t.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
				var request dagger.Request
				require.NoError(t, json.NewDecoder(req.Body).Decode(&request))
				var data any
				switch {
				case strings.Contains(request.Query, "currentWorkspace"):
					workspaceReads++
					// A second effectful workspace read really has another identity.
					data = map[string]any{"currentWorkspace": map[string]any{"id": fmt.Sprintf("workspace-%d", workspaceReads)}}
				case strings.Contains(request.Query, "__itemsJSON"):
					data = map[string]any{"node": map[string]any{"items": string(items)}}
				case strings.Contains(request.Query, "dimensionDefinitions"):
					dimensionReads++
					require.Equal(t, "global-artifacts", request.Variables.(map[string]any)["id"], "aliases must use unfiltered definitions")
					data = map[string]any{"node": map[string]any{"dimensionDefinitions": globalDimensions}}
				case strings.Contains(request.Query, "node") && strings.Contains(request.Query, `"global-artifacts"`):
					data = map[string]any{"node": map[string]any{"id": "global-artifacts"}}
				case strings.Contains(request.Query, "artifacts"):
					require.Contains(t, request.Query, `"workspace-1"`, "every projection must use the original workspace identity")
					var fields any
					if strings.Contains(request.Query, "filterCheckCommand") {
						fields = map[string]any{"filterCheckCommand": map[string]any{"id": "selected-artifacts"}}
					} else {
						globalCatalogReads++
						require.NotContains(t, request.Query, "include:", "formatting must request the global catalog")
						fields = map[string]any{"id": "global-artifacts"}
					}
					data = map[string]any{"node": map[string]any{"artifacts": fields}}
				default:
					return nil, fmt.Errorf("unexpected query: %s", request.Query)
				}
				body, err := json.Marshal(map[string]any{"data": data})
				require.NoError(t, err)
				return &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(bytes.NewReader(body))}, nil
			}}))
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, dag.Close()) })
			cmd := &cobra.Command{Use: "check"}
			registerCommandArtifactFlags(cmd)
			cmd.Flags().Bool("generated", true, "")
			require.NoError(t, cmd.Flags().Set("all", "true"))
			var stdout, stderr bytes.Buffer
			cmd.SetOut(&stdout)
			cmd.SetErr(&stderr)
			selection, workspace, err := commandArtifactsWithFlags(t.Context(), dag, dag.CurrentWorkspace(), cmd, tc.addresses, false)
			require.NoError(t, err)
			err = listArtifactSelection(t.Context(), dag, workspace, selection.FilterCheckCommand(), cmd)
			require.NoError(t, err)
			require.Equal(t, 1, workspaceReads)
			if len(tc.keys) > 0 {
				require.Equal(t, 1, globalCatalogReads)
				require.Equal(t, 1, dimensionReads)
			} else {
				require.Zero(t, globalCatalogReads)
				require.Zero(t, dimensionReads)
			}
			for _, flag := range tc.flags {
				require.Contains(t, stdout.String(), flag)
			}
			require.Contains(t, stdout.String(), "dag+check://"+tc.path)
			require.NotContains(t, stdout.String(), "--module=")
			require.NotContains(t, stdout.String(), "--test=")
			require.Empty(t, stderr.String())
		})
	}
}
