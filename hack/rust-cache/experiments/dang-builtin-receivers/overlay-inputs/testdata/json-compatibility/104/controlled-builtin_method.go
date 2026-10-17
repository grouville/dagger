package dang

import (
	"context"
	"fmt"
)

// Registered methods accept the receiver as a value, so binding them does not
// require an evaluation scope. BuiltinFunction supplies the callable metadata.
// Hand-written BuiltinFunction callbacks still receive their original scope.
type builtinMethod struct {
	BuiltinFunction
	callReceiver func(context.Context, Value, map[string]Value) (Value, error)
}

func (m builtinMethod) Call(ctx context.Context, scope ValueScope, args map[string]Value) (Value, error) {
	receiver, _ := scope.Self()
	return m.callReceiver(ctx, receiver, args)
}

type boundBuiltinMethod struct {
	builtinMethod
	receiver Value
}

func (m boundBuiltinMethod) Call(ctx context.Context, _ ValueScope, args map[string]Value) (Value, error) {
	if !directBuiltinReceiverForCall() {
		scope := NewObject(NewType("_temp_", ObjectKind))
		scope.EnterSelf(m.receiver)
		return m.BuiltinFunction.Call(ctx, scope, args)
	}
	return m.callReceiver(ctx, m.receiver, args)
}

func (m boundBuiltinMethod) String() string {
	return fmt.Sprintf("bound_builtin_method(%s)", m.builtinMethod.String())
}

func (boundBuiltinMethod) MarshalJSON() ([]byte, error) {
	return nil, fmt.Errorf("cannot marshal bound builtin method value")
}

func bindBuiltinMethod(method, receiver Value) (Callable, bool) {
	switch method := method.(type) {
	case builtinMethod:
		return boundBuiltinMethod{builtinMethod: method, receiver: receiver}, true
	case BuiltinFunction:
		return BoundBuiltinMethod{Method: method, Receiver: receiver}, true
	default:
		return nil, false
	}
}
