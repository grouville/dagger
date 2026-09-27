package server

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func TestCurrentTypeDefsJSONWorkspaceDemand(t *testing.T) {
	foo := pendingModule{Kind: moduleLoadKindAmbient, Name: "foo"}
	bar := pendingModule{Kind: moduleLoadKindAmbient, Name: "barBaz"}
	entry := pendingModule{Kind: moduleLoadKindAmbient, Name: "entry", Entrypoint: true}
	mods := []pendingModule{foo, bar, entry}
	for _, field := range []string{"currentTypeDefs", "__currentTypeDefsJSON"} {
		t.Run(field, func(t *testing.T) {
			require.True(t, rootFieldsRequireFullWorkspaceSchema([]string{field}))
			require.Equal(t, mods, filterPendingWorkspaceModulesForRootFields(mods, nil, nil, []string{field}))
			for _, tc := range []struct {
				name, scope          string
				pending, want        []pendingModule
				extra                []string
				served               map[string]struct{}
				entryServed, applied bool
			}{
				{name: "no scope", pending: mods, want: mods},
				{name: "scoped module plus entrypoint", scope: "foo", pending: mods, want: []pendingModule{foo, entry}, applied: true},
				{name: "kebab module", scope: "bar-baz", pending: mods, want: []pendingModule{bar, entry}, applied: true},
				{name: "unknown entrypoint command", scope: "greet", pending: mods, want: []pendingModule{entry}, applied: true},
				{name: "other full schema demand", scope: "foo", pending: mods, want: mods, extra: []string{"__schema"}},
				{name: "union explicit module", scope: "foo", pending: mods, want: mods, extra: []string{"barBaz"}, applied: true},
				{name: "served module", scope: "already", pending: mods, want: []pendingModule{entry}, served: map[string]struct{}{"already": {}}, applied: true},
				{name: "served entrypoint", scope: "greet", pending: []pendingModule{foo, bar}, want: []pendingModule{}, served: map[string]struct{}{"entry": {}}, entryServed: true, applied: true},
			} {
				t.Run(tc.name, func(t *testing.T) {
					selected, applied := filterPendingWorkspaceModulesForScopedRootFields(tc.pending, tc.served, nil, append([]string{field}, tc.extra...), tc.scope, tc.entryServed)
					require.Equal(t, tc.want, selected)
					require.Equal(t, tc.applied, applied)
				})
			}
		})
	}
}

func TestCurrentTypeDefsJSONAliasedRequestConsumesScope(t *testing.T) {
	for _, field := range []string{"currentTypeDefs", "__currentTypeDefsJSON"} {
		t.Run(field, func(t *testing.T) {
			query := "{ metadata: " + field
			if field == "currentTypeDefs" {
				query += " { name }"
			}
			query += " }"
			body, err := json.Marshal(map[string]string{"query": query})
			require.NoError(t, err)
			req := httptest.NewRequest(http.MethodPost, engine.QueryEndpoint, strings.NewReader(string(body)))
			req.Header.Set("Content-Type", "application/json")
			ok, fields, err := dagql.PeekRootFields(req)
			require.NoError(t, err)
			require.True(t, ok)
			require.Equal(t, []string{field}, fields)
			client := &clientRuntime{clientRecord: &clientRecord{clientID: "client", clientMetadata: &engine.ClientMetadata{LoadWorkspaceModules: true, WorkspaceModuleScope: "good"}}, pendingWorkspaceLoad: true, pendingModules: []pendingModule{{Kind: moduleLoadKindAmbient, Name: "unrelated"}}, servedWorkspaceModuleNames: map[string]struct{}{"good": {}}}
			require.NoError(t, (&Server{}).ensureRequestModulesLoaded(context.Background(), client, req))
			client.modulesMu.Lock()
			defer client.modulesMu.Unlock()
			require.Empty(t, client.pendingWorkspaceModuleScopeLocked(), "metadata consumed the one-shot scope even though its target is already served")
			require.Len(t, client.pendingModules, 1, "unrelated module must remain unloaded")
			require.Equal(t, "unrelated", client.pendingModules[0].Name)
		})
	}
}
