package core

import (
	"testing"

	"github.com/dagger/dagger/core/modules"
	"github.com/stretchr/testify/require"
)

func TestApplyLegacyCustomizationsToTypeDefs(t *testing.T) {
	dirType := (&TypeDef{}).WithObject("Directory", "", nil, nil)
	stringType := &TypeDef{Kind: TypeDefKindString}

	mainObj := (&TypeDef{}).WithObject("toolchain", "", nil, nil)

	ctor := NewFunction("new", mainObj).
		WithArg("config", dirType, "", nil, "", "", nil, nil, nil)
	var err error
	mainObj, err = mainObj.WithObjectConstructor(ctor)
	require.NoError(t, err)

	configuredObj := (&TypeDef{}).WithObject("configured", "", nil, nil)

	check := NewFunction("check", stringType).
		WithArg("version", stringType, "", nil, "", "", nil, nil, nil)
	configuredObj, err = configuredObj.WithFunction(check)
	require.NoError(t, err)

	configure := NewFunction("configure", configuredObj)
	mainObj, err = mainObj.WithFunction(configure)
	require.NoError(t, err)

	mod := &Module{
		NameField:    "toolchain",
		OriginalName: "toolchain",
		ObjectDefs:   []*TypeDef{mainObj, configuredObj},
	}

	mod.ApplyLegacyCustomizationsToTypeDefs([]*modules.ModuleConfigArgument{
		{
			Argument:    "config",
			DefaultPath: "./custom-config.txt",
			Ignore:      []string{"node_modules"},
		},
		{
			Function: []string{"configure", "check"},
			Argument: "version",
			Default:  "1.24.1",
		},
	})

	mainObject, ok := mod.MainObject()
	require.True(t, ok)
	require.True(t, mainObject.Constructor.Valid)

	configArg, ok := lookupFunctionArg(mainObject.Constructor.Value, "config")
	require.True(t, ok)
	require.Equal(t, "./custom-config.txt", configArg.DefaultPath)
	require.Equal(t, []string{"node_modules"}, configArg.Ignore)
	require.True(t, configArg.TypeDef.Optional)

	configured, ok := mod.ObjectByOriginalName("configured")
	require.True(t, ok)
	checkFn, ok := functionByOriginalName(configured, "check")
	require.True(t, ok)

	versionArg, ok := lookupFunctionArg(checkFn, "version")
	require.True(t, ok)
	require.Equal(t, `"1.24.1"`, versionArg.DefaultValue.String())
}

func TestApplyLegacyCustomizationsWildcardMatchesAll(t *testing.T) {
	mod := newLegacyHelloModule(t)

	mod.ApplyLegacyCustomizationsToTypeDefs([]*modules.ModuleConfigArgument{
		{
			Function: []string{"*"},
			Argument: "message",
			Default:  "hola",
		},
	})

	helloObj, ok := mod.MainObject()
	require.True(t, ok)
	configurable, ok := functionByOriginalName(helloObj, "configurableMessage")
	require.True(t, ok)
	configArg, ok := lookupFunctionArg(configurable, "message")
	require.True(t, ok)
	require.Equal(t, `"hola"`, configArg.DefaultValue.String())

	shout, ok := functionByOriginalName(helloObj, "shoutMessage")
	require.True(t, ok)
	shoutArg, ok := lookupFunctionArg(shout, "message")
	require.True(t, ok)
	require.Equal(t, `"hola"`, shoutArg.DefaultValue.String())
}

func TestApplyLegacyCustomizationsSpecificOverrides(t *testing.T) {
	mod := newLegacyHelloModule(t)

	mod.ApplyLegacyCustomizationsToTypeDefs([]*modules.ModuleConfigArgument{
		{
			Function: []string{"*"},
			Argument: "message",
			Default:  "hola",
		},
		{
			Function: []string{"configurableMessage"},
			Argument: "message",
			Default:  "bonjour",
		},
	})

	helloObj, ok := mod.MainObject()
	require.True(t, ok)
	configurable, ok := functionByOriginalName(helloObj, "configurableMessage")
	require.True(t, ok)
	configArg, ok := lookupFunctionArg(configurable, "message")
	require.True(t, ok)
	require.Equal(t, `"bonjour"`, configArg.DefaultValue.String())

	shout, ok := functionByOriginalName(helloObj, "shoutMessage")
	require.True(t, ok)
	shoutArg, ok := lookupFunctionArg(shout, "message")
	require.True(t, ok)
	require.Equal(t, `"hola"`, shoutArg.DefaultValue.String())
}

func TestApplyLegacyCustomizationsChainedGlob(t *testing.T) {
	mod := newLegacyHelloModule(t)

	mod.ApplyLegacyCustomizationsToTypeDefs([]*modules.ModuleConfigArgument{
		{
			Function: []string{"gre*", "pla*"},
			Argument: "planet",
			Default:  "Mars",
		},
	})

	greetings, ok := mod.ObjectByOriginalName("greetings")
	require.True(t, ok)
	planet, ok := functionByOriginalName(greetings, "planet")
	require.True(t, ok)
	planetArg, ok := lookupFunctionArg(planet, "planet")
	require.True(t, ok)
	require.Equal(t, `"Mars"`, planetArg.DefaultValue.String())
}

func newLegacyHelloModule(t *testing.T) *Module {
	stringType := &TypeDef{Kind: TypeDefKindString}
	greetingsType := (&TypeDef{}).WithObject("greetings", "", nil, nil)
	planet := NewFunction("planet", stringType).
		WithArg("planet", stringType, "", nil, "", "", nil, nil, nil)
	var err error
	greetingsType, err = greetingsType.WithFunction(planet)
	require.NoError(t, err)

	helloObj := (&TypeDef{}).WithObject("hello", "", nil, nil)
	configurable := NewFunction("configurableMessage", stringType).
		WithArg("message", stringType, "", nil, "", "", nil, nil, nil)
	shout := NewFunction("shoutMessage", stringType).
		WithArg("message", stringType, "", nil, "", "", nil, nil, nil)
	greet := NewFunction("greet", greetingsType)
	helloObj, err = helloObj.WithFunction(configurable)
	require.NoError(t, err)
	helloObj, err = helloObj.WithFunction(shout)
	require.NoError(t, err)
	helloObj, err = helloObj.WithFunction(greet)
	require.NoError(t, err)

	return &Module{
		NameField:    "hello",
		OriginalName: "hello",
		ObjectDefs:   []*TypeDef{helloObj, greetingsType},
	}
}
