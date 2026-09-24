package core

import (
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/stretchr/testify/require"
)

func defaultTestObject[T dagql.Typed](t testing.TB, self T) dagql.ObjectResult[T] {
	t.Helper()
	res, err := dagql.NewResultForCall(self, &dagql.ResultCall{})
	require.NoError(t, err)
	return dagql.ObjectResult[T]{Result: res}
}

func TestUserDefaultWithoutDotEnv(t *testing.T) {
	for _, tc := range []struct {
		name     string
		source   *ModuleSource
		wantRead bool
	}{
		{name: "no source"},
		{name: "no defaults", source: &ModuleSource{}},
		{name: "empty defaults", source: &ModuleSource{UserDefaults: NewEnvFile(true)}},
		{name: "nonempty defaults", source: &ModuleSource{UserDefaults: NewEnvFile(true).WithVariable("GREETING", "hello")}, wantRead: true},
		{name: "expansion context", source: &ModuleSource{UserDefaults: &EnvFile{Context: []string{"ROOT=hello"}}}, wantRead: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			mod := &Module{OriginalName: "Example"}
			if tc.source != nil {
				mod.Source = dagql.NonNull(defaultTestObject(t, tc.source))
			}
			fn := &ModuleFunction{
				mod:    defaultTestObject(t, mod),
				objDef: &ObjectTypeDef{OriginalName: "Example"},
				metadata: &Function{Args: dagql.ObjectResultArray[*FunctionArg]{
					defaultTestObject(t, &FunctionArg{Name: "greeting", OriginalName: "greeting"}),
				}},
			}
			// No query/server in this context: empty defaults must not need
			// a parent client, while nonempty defaults must still resolve it.
			value, found, err := fn.UserDefault(t.Context(), "greeting")
			if tc.wantRead {
				require.ErrorContains(t, err, "get current query")
			} else {
				require.NoError(t, err)
			}
			require.False(t, found)
			require.Nil(t, value)

			_, _, err = fn.UserDefault(t.Context(), "unknown")
			require.ErrorContains(t, err, "has no argument")

			mod.WorkspaceConfig = map[string]any{"greeting": "from settings"}
			value, found, err = fn.UserDefault(t.Context(), "greeting")
			require.NoError(t, err)
			require.True(t, found)
			require.Equal(t, "from settings", value.UserInput)

			mod.WorkspaceConfig = map[string]any{}
			mod.DefaultsFromDotEnv = false
			value, found, err = fn.UserDefault(t.Context(), "greeting")
			require.NoError(t, err)
			require.False(t, found)
			require.Nil(t, value)
		})
	}
}
