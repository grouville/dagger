package daggercmd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"slices"
	"strings"
	"testing"

	"dagger.io/dagger"
	"github.com/dagger/dagger/core/artifact"
	"github.com/dagger/dagger/core/dagaddress"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/require"
)

func TestListedArtifactKeysPreservesDimensionAndOrder(t *testing.T) {
	for _, size := range []int{0, 1, 8, 9, 100} {
		t.Run(fmt.Sprint(size), func(t *testing.T) {
			var items []listedArtifact
			var want []dagaddress.Pair
			for i := range size {
				key := fmt.Sprintf("test %d", i)
				if i == 0 {
					key = "" // An empty key is still a key.
				}
				for _, dimension := range []string{"Go.tests", "Dang.tests"} {
					items = append(items, listedArtifact{DimensionKeys: []struct{ Dimension, Key string }{
						{dimension, key}, {dimension, key},
					}})
					want = append(want, dagaddress.Pair{Dimension: dimension, Key: key, HasKey: true})
				}
			}
			// Duplicates recur after the membership index has been constructed.
			items = append(items, slices.Clone(items)...)
			before, err := json.Marshal(items)
			require.NoError(t, err)
			require.Equal(t, want, listedArtifactKeys(items))
			after, err := json.Marshal(items)
			require.NoError(t, err)
			require.Equal(t, before, after, "formatting must not mutate discovery results")
		})
	}
}

// Exercise the actual expanded listing formatter, including decoding, grouping,
// dimension aliases, and command output. The fake transport excludes engine and
// network time so that CLI scaling can be measured independently.
func BenchmarkListArtifactSelectionAll(b *testing.B) {
	for _, size := range []int{14, 100, 1000, 10000} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			var items []listedArtifact
			for i := range size {
				items = append(items, listedArtifact{
					URI: "dag+check://go/modules/tests/run", Description: "Run this test.",
					DimensionKeys: []struct{ Dimension, Key string }{
						{"Go.modules", "."}, {"Go.tests", fmt.Sprintf("Test%05d", i)},
					},
				})
			}
			encoded, err := json.Marshal(items)
			require.NoError(b, err)
			payload := func(data any) []byte {
				body, err := json.Marshal(map[string]any{"data": data})
				require.NoError(b, err)
				return body
			}
			itemResponse := payload(map[string]any{"node": map[string]any{"items": string(encoded)}})
			dimensionResponse := payload(map[string]any{"node": map[string]any{"dimensionDefinitions": artifact.Dimensions{
				{Identifier: "Go.modules", Name: "module", QualifiedName: "go-module"},
				{Identifier: "Go.tests", Name: "test", QualifiedName: "go-test"},
			}}})
			catalogResponse := payload(map[string]any{"node": map[string]any{"artifacts": map[string]any{"id": "global-artifacts"}}})
			idResponse := payload(map[string]any{"node": map[string]any{"id": "global-artifacts"}})
			dag, err := dagger.Connect(b.Context(), dagger.WithConn(agentTestConn{do: func(req *http.Request) (*http.Response, error) {
				var query dagger.Request
				if err := json.NewDecoder(req.Body).Decode(&query); err != nil {
					return nil, err
				}
				var body []byte
				switch {
				case strings.Contains(query.Query, "__itemsJSON"):
					body = itemResponse
				case strings.Contains(query.Query, "dimensionDefinitions"):
					body = dimensionResponse
				case strings.Contains(query.Query, "artifacts") && strings.Contains(query.Query, `"workspace-1"`):
					body = catalogResponse
				case strings.Contains(query.Query, "node"):
					body = idResponse
				default:
					return nil, fmt.Errorf("unexpected query: %s", query.Query)
				}
				return &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(bytes.NewReader(body))}, nil
			}}))
			require.NoError(b, err)
			b.Cleanup(func() { require.NoError(b, dag.Close()) })
			cmd := &cobra.Command{Use: "check"}
			registerCommandArtifactFlags(cmd)
			cmd.Flags().Bool("generated", true, "")
			require.NoError(b, cmd.Flags().Set("all", "true"))
			cmd.SetOut(io.Discard)
			cmd.SetErr(io.Discard)
			ws := dagger.Ref[*dagger.Workspace](dag, "workspace-1")
			selection := dagger.Ref[*dagger.Artifacts](dag, "selected-artifacts")
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				if err := listArtifactSelection(b.Context(), dag, ws, selection, cmd); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
