package dagql

import "context"

// Plain data selections can read an inline value while the enclosing operation
// retains its list. Selections needing object identity use normal NthValue.
func (s *Server) canProjectScalarList(parent AnyResult, sels []Selection) bool {
	if _, ok := parent.Unwrap().(valueEnumerable); !ok {
		return false
	}
	shared := parent.cacheSharedResult()
	if shared == nil || shared.id == 0 {
		return false
	}
	typ := parent.Type()
	if typ == nil || typ.Elem == nil {
		return false
	}
	class, ok := s.ObjectType(typ.Elem.Name())
	if !ok {
		return false
	}
	policy, ok := class.(interface{ scalarProjectionSafe() bool })
	if !ok || !policy.scalarProjectionSafe() {
		return false
	}
	for _, sel := range sels {
		if len(sel.Subselections) != 0 || len(sel.TypeConditions) != 0 || len(sel.Selector.Args) != 0 || sel.Selector.Nth != 0 {
			return false
		}
		field, ok := class.FieldSpec(sel.Selector.Field, sel.Selector.View)
		if !ok || !field.Trivial || !trivialBuiltinScalar(field.Type) || field.GetDynamicInput != nil || len(field.ImplicitInputs) != 0 || len(field.Args.Inputs(sel.Selector.View)) != 0 {
			return false
		}
	}
	return true
}

func (s *Server) projectScalarListItem(ctx context.Context, parent AnyResult, values Enumerable, nth int) (AnyResult, error) {
	value, err := values.Nth(nth)
	if err != nil {
		return nil, err
	}
	inner := leafValue(value)
	if inner == nil {
		return nil, nil
	}
	if _, ok := inner.(AnyResult); ok {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	if _, ok := inner.(HasPartHostBinding); ok {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	if _, ok := inner.(HasPartHost); ok {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	if _, ok := inner.(OnReleaser); ok {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	if inner.Type().Name() != parent.Type().Elem.Name() {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	shared := parent.cacheSharedResult()
	frame := shared.loadResultCall()
	if frame == nil || frame.Type == nil || frame.Type.Elem == nil {
		return s.loadNthValue(ctx, parent, nth, false)
	}
	frame = frame.fork()
	frame.Type = frame.Type.Elem.clone()
	frame.Receiver = &ResultCallRef{ResultID: uint64(shared.id), shared: shared}
	frame.Nth = int64(nth)
	result := newDetachedResult[Typed](frame, value)
	if inner, ok := result.DerefValue(); ok {
		return inner, nil
	}
	return nil, nil
}
