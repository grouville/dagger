package schema

import (
	"slices"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/stretchr/testify/require"
)

func TestArtifactStaticModulePruning(t *testing.T) {
	known := []string{"backend", "go", "dagger-go-sdk", "otherSdk"}
	for _, tc := range []struct {
		name    string
		include []string
		want    []string
	}{
		{"typed backend address", []string{"backend:go-test-base"}, []string{"backend"}},
		{"selected collection check", []string{"go:modules:tests:run"}, []string{"go"}},
		{"generator alias", []string{"daggerGoSdk:generate:stale"}, []string{"dagger-go-sdk"}},
		{"multiple module prefixes", []string{"Backend:source", "other-sdk:generate"}, []string{"backend", "otherSdk"}},
		{"unfiltered", nil, known},
		{"empty filter", []string{}, known},
		{"unqualified entrypoint", []string{"generate"}, known},
		{"unknown prefix preserves fallback", []string{"missing:run"}, known},
		{"one unknown preserves fallback", []string{"backend:source", "missing:run"}, known},
		{"wildcard prefix", []string{"*:generate"}, known},
		{"wildcard suffix", []string{"backend:**"}, known},
		{"union", []string{"{backend,go}:run"}, known},
		{"invalid pattern retains ordinary error", []string{"backend:["}, known},
		{"escaped pattern", []string{`backend:\*`}, known},
	} {
		t.Run(tc.name, func(t *testing.T) {
			beforeNames, beforeInclude := slices.Clone(known), slices.Clone(tc.include)
			selection := artifactIncludedModuleNames(known, tc.include)
			var got []string
			for _, name := range known {
				if artifactIncludesModule(selection, name, false) {
					got = append(got, name)
				}
				// Entrypoints can expose a path whose first component is the
				// name of a different configured module. Never prune them.
				require.True(t, artifactIncludesModule(selection, name, true))
			}
			require.Equal(t, tc.want, got)
			require.Equal(t, beforeNames, known)
			require.Equal(t, beforeInclude, tc.include)
		})
	}
}

// Use the existing complete matcher as the oracle. The prefilter may retain
// extra metadata trees, but must not remove a tree with any matching node.
// Collection get nodes have transparent paths, and promoted entrypoint paths
// can collide with another module's name.
func TestArtifactStaticPruningPreservesCompleteMatcher(t *testing.T) {
	known := []string{"backend", "go", "dagger-go-sdk", "app"}
	patterns := [][]string{
		nil, {"backend"}, {"Backend:goTestBase"}, {"backend:source"},
		{"go:modules:tests:run"}, {"daggerGoSdk:generate:stale"},
		{"app"}, {"generate"}, {"go:modules", "backend:source"},
		{"go:*"}, {"**:run"}, {"{go,backend}:**"}, {"unknown:run"},
		{"backend:["},
	}
	for _, entrypoint := range []bool{false, true} {
		for _, module := range known {
			root := &core.ModTreeNode{Name: module, Parent: &core.ModTreeNode{}, WorkspaceEntrypoint: entrypoint}
			generate := &core.ModTreeNode{Name: "generate", Parent: root}
			modules := &core.ModTreeNode{Name: "modules", Parent: root}
			getModule := &core.ModTreeNode{Parent: modules, Name: "get", CollectionDimension: &core.ArtifactDimension{Identifier: "M.modules"}}
			tests := &core.ModTreeNode{Name: "tests", Parent: getModule}
			getTest := &core.ModTreeNode{Parent: tests, Name: "get", CollectionDimension: &core.ArtifactDimension{Identifier: "I.tests"}}
			collision := &core.ModTreeNode{Name: "backend", Parent: root}
			nodes := []*core.ModTreeNode{root, generate,
				{Name: "stale", Parent: generate},
				{Name: "source", Parent: root},
				{Name: "goTestBase", Parent: root}, modules, tests,
				{Name: "run", Parent: getTest},
				{Name: "goTestBase", Parent: collision},
			}
			for _, include := range patterns {
				keep := artifactIncludesModule(artifactIncludedModuleNames(known, include), module, entrypoint)
				for _, node := range nodes {
					match, err := matchWorkspaceInclude(t.Context(), node, include)
					if match || err != nil {
						require.True(t, keep, "module=%s entrypoint=%v path=%v include=%v match=%v err=%v", module, entrypoint, node.Path(), include, match, err)
					}
				}
			}
		}
	}
}

// Schema serving accepts a module with no main object, but constructing its
// artifact tree rejects it. Targeted discovery must not depend on whether an
// unrelated module happened to be served earlier in the session. Selected,
// entrypoint and non-narrowed validation errors remain visible.
func TestArtifactStaticPruningScopesServedModuleValidation(t *testing.T) {
	ctx := t.Context()
	srv, err := dagql.NewServer(ctx, &core.Query{})
	require.NoError(t, err)
	srv.InstallObject(dagql.NewClass(srv, dagql.ClassOpts[*core.Module]{}))
	mod := &core.Module{NameField: "unrelated", OriginalName: "Unrelated"}
	served, err := dagql.NewObjectResultForCall(mod, srv, &dagql.ResultCall{
		Field: "servedEmptyModule", Type: dagql.NewResultCallType(mod.Type()),
	})
	require.NoError(t, err)
	require.NoError(t, core.NewUserMod(served).Install(ctx, srv), "the module can be served before discovery")
	_, _, err = core.ModuleArtifactNodes(ctx, served)
	require.ErrorContains(t, err, `"unrelated": no main object`, "the real tree builder detects the late error")
	for _, tc := range []struct {
		name          string
		include       []string
		entrypoint    bool
		wantTreeError bool
	}{
		{"unrelated literal selection", []string{"backend:source"}, false, false},
		{"selected module", []string{"unrelated:source"}, false, true},
		{"unfiltered catalog", nil, false, true},
		{"entrypoint can expose selected path", []string{"backend:source"}, true, true},
		{"pattern keeps complete validation", []string{"backend:**"}, false, true},
		{"unknown prefix keeps fallback", []string{"missing:source"}, false, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			selection := artifactIncludedModuleNames([]string{"backend", "unrelated"}, tc.include)
			var treeErr error
			if artifactIncludesModule(selection, served.Self().Name(), tc.entrypoint) {
				_, _, treeErr = core.ModuleArtifactNodes(t.Context(), served)
			}
			if tc.wantTreeError {
				require.ErrorContains(t, treeErr, `"unrelated": no main object`)
			} else {
				require.NoError(t, treeErr)
			}
		})
	}
}
