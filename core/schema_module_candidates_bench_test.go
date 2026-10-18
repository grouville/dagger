package core

import (
	"fmt"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/stretchr/testify/require"
)

func BenchmarkModDepsForCallCandidates(b *testing.B) {
	for _, modules := range []int{0, 2, 64} {
		for _, kind := range []string{"core", "module"} {
			b.Run(fmt.Sprintf("%s/%d", kind, modules), func(b *testing.B) {
				env := newPersistedFamiliesTestEnv(b, "bench")
				ctx, cache, srv := env.open(b)
				installPreferenceScope(b, srv)
				query, err := CurrentQuery(ctx)
				require.NoError(b, err)
				mods := make([]Mod, modules)
				for i := range modules {
					name := fmt.Sprintf("module-%d", i)
					mods[i] = NewUserMod(preferenceModule(b, env, ctx, cache, srv, name, name))
				}
				facade := &installedPreferenceServer{
					persistedFamiliesTestQueryServer: query.Server.(*persistedFamiliesTestQueryServer),
					served:                           NewSchemaBuilder(query, mods),
				}
				query.Server = facade
				frame := &dagql.ResultCall{
					Kind:  dagql.ResultCallKindField,
					Field: "name",
					Type:  dagql.NewResultCallType(dagql.String("").Type()),
				}
				if kind == "module" {
					var target dagql.ObjectResult[*Module]
					if modules == 0 {
						target = preferenceModule(b, env, ctx, cache, srv, "unserved", "unserved")
					} else {
						target = mods[0].ModuleResult()
					}
					id, err := cache.PersistedResultID(target)
					require.NoError(b, err)
					frame.Module = &dagql.ResultCallModule{Name: target.Self().Name(), ResultRef: &dagql.ResultCallRef{ResultID: id}}
				}
				// Populate the same scoped results and schema memo before measuring.
				_, err = query.ModDepsForCall(ctx, frame)
				require.NoError(b, err)
				b.ReportAllocs()
				for b.Loop() {
					_, err := query.ModDepsForCall(ctx, frame)
					if err != nil {
						b.Fatal(err)
					}
				}
			})
		}
	}
}
