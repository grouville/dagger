package dang

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func builtinReceiverTestCall(t testing.TB, scope ValueScope, source string) Callable {
	t.Helper()
	parsed, err := ParseWithRecovery("receiver-test", []byte(source))
	if err != nil {
		t.Fatal(err)
	}
	value, err := EvalNode(context.Background(), scope, parsed.(*FileBlock).Forms[0])
	if err != nil {
		t.Fatal(err)
	}
	callable, ok := value.(Callable)
	if !ok {
		t.Fatalf("selection returned %T, want Callable", value)
	}
	return callable
}

func TestBuiltinReceiverDefaultsAndContext(t *testing.T) {
	previous := builtins
	builtins = newBuiltinRegistry()
	t.Cleanup(func() { builtins = previous })
	wantBlock := true
	def := BuiltinDef{
		Name: "receiverProbe", IsMethod: true, ReceiverType: StringType,
		ParamTypes: []ParamDef{
			{Name: "required", Type: NonNull(StringType)},
			{Name: "suffix", Type: NonNull(StringType), DefaultValue: StringValue{Val: "!"}},
		},
		ReturnType: NonNull(StringType),
		Impl: func(ctx context.Context, receiver Value, args Args) (Value, error) {
			if (args.Block != nil) != wantBlock {
				t.Fatalf("block present = %v, want %v", args.Block != nil, wantBlock)
			}
			if ctx.Value(contextKey("receiver-test")) != "context" {
				t.Fatal("callback lost context")
			}
			return StringValue{Val: receiver.(StringValue).Val + args.Values["required"].(StringValue).Val + args.Values["suffix"].(StringValue).Val}, nil
		},
	}
	Register(def)
	scope := NewObject(NewType("test", ObjectKind))
	addBuiltinFunctions(scope)
	first := builtinReceiverTestCall(t, scope, `"first".receiverProbe`)
	second := builtinReceiverTestCall(t, scope, `"second".receiverProbe`)
	ctx := context.WithValue(t.Context(), contextKey("receiver-test"), "context")
	args := map[string]Value{"required": StringValue{Val: " value"}}
	value, err := first.Call(ContextWithBlock(ctx, FunctionValue{}), scope, args)
	if err != nil {
		t.Fatal(err)
	}
	if got := value.(StringValue).Val; got != "first value!" {
		t.Fatalf("got %q", got)
	}
	if len(args) != 1 {
		t.Fatalf("defaults mutated caller arguments: %v", args)
	}
	wantBlock = false
	value, err = second.Call(ctx, scope, map[string]Value{"required": StringValue{Val: " value"}, "suffix": StringValue{Val: "."}})
	if err != nil {
		t.Fatal(err)
	}
	if got := value.(StringValue).Val; got != "second value." {
		t.Fatalf("got %q", got)
	}
}

func TestBuiltinReceiverCustomScope(t *testing.T) {
	scope := NewObject(NewType("caller", ObjectKind))
	scope.Bind("outside", StringValue{Val: "hidden"}, PublicVisibility)
	scope.EnterSelf(StringValue{Val: "caller"})
	var seen []*Object
	fn := BuiltinFunction{
		Name:   "receiverProbe",
		FnType: createFunctionTypeFromDef(BuiltinDef{ParamTypes: []ParamDef{{Name: "required", Type: NonNull(StringType)}}, ReturnType: NonNull(StringType)}),
		CallFn: func(_ context.Context, callback ValueScope, _ map[string]Value) (Value, error) {
			object, ok := callback.(*Object)
			if !ok {
				t.Fatalf("custom callback received %T", callback)
			}
			if callback.Has("outside") || callback.Has("scratch") {
				t.Fatal("custom callback inherited another scope")
			}
			value, _ := callback.Self()
			callback.Bind("scratch", StringValue{Val: "local"}, PrivateVisibility)
			callback.MutateSelf(StringValue{Val: "mutated"})
			seen = append(seen, object)
			return value, nil
		},
	}
	scope.Bind(GetMethodKey(StringType, "receiverProbe"), fn, PrivateVisibility)
	for _, source := range []string{`"first".receiverProbe`, `"second".receiverProbe`} {
		callable := builtinReceiverTestCall(t, scope, source)
		value, err := callable.Call(t.Context(), scope, nil)
		if err != nil {
			t.Fatal(err)
		}
		want := "first"
		if len(seen) == 2 {
			want = "second"
		}
		if got := value.(StringValue).Val; got != want {
			t.Fatalf("got receiver %q, want %q", got, want)
		}
	}
	if seen[0] == seen[1] {
		t.Fatal("custom callback reused its local scope")
	}
	value, _ := scope.Self()
	if got := value.(StringValue).Val; got != "caller" {
		t.Fatalf("custom callback changed caller self to %q", got)
	}
}

func TestBuiltinReceiverCallableMetadata(t *testing.T) {
	scope := NewObject(NewType("test", ObjectKind))
	addBuiltinFunctions(scope)
	fn := builtinReceiverTestCall(t, scope, `"receiver".hasPrefix`)
	if got := fn.String(); got != "bound_builtin_method(builtin:hasPrefix)" {
		t.Fatalf("got callable name %q", got)
	}
	names := fn.ParameterNames()
	if len(names) != 1 || names[0] != "prefix" || fn.IsAutoCallable() {
		t.Fatalf("unexpected callable metadata: names=%v, auto=%v", names, fn.IsAutoCallable())
	}
	method, ok, err := scope.Lookup(t.Context(), GetMethodKey(StringType, "hasPrefix"))
	if err != nil || !ok {
		t.Fatalf("lookup method: found=%v, err=%v", ok, err)
	}
	if got, want := fn.Type().String(), method.Type().String(); got != want {
		t.Fatalf("bound type %s, want %s", got, want)
	}
	if _, err := json.Marshal(fn); err == nil || !strings.HasSuffix(err.Error(), ": cannot marshal bound builtin method value") {
		t.Fatalf("unexpected serialization error: %v", err)
	}
}
