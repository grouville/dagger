package dagql

import (
	"encoding/json"
	"fmt"
)

// persistedScalarArray retains plain values and one independent producer call.
// Like the result-backed decoder, NthValue uses the recorded call even when
// its caller supplies no frame or a different one.
type persistedScalarArray struct {
	DynamicArrayOutput
	frame *ResultCall
}

func (a persistedScalarArray) NthValue(i int, _ *ResultCall) (AnyResult, error) {
	return a.DynamicArrayOutput.NthValue(i, a.frame)
}

// encodeItems preserves the scalar envelopes without materializing element
// results again while saving the compact representation.
func (a persistedScalarArray) encodeItems() ([]PersistedResultEnvelope, []PersistedSnapshotRefLink, error) {
	items := make([]PersistedResultEnvelope, len(a.Values))
	for i, value := range a.Values {
		payload, err := json.Marshal(value)
		if err != nil {
			return nil, nil, fmt.Errorf("encode persisted list item %d envelope: encode scalar_json payload: %w", i+1, err)
		}
		items[i] = PersistedResultEnvelope{
			Version:    persistedResultEnvelopeVersion,
			Kind:       persistedResultKindScalar,
			TypeName:   value.Type().Name(),
			ScalarJSON: payload,
		}
	}
	return items, nil, nil
}

// decodePersistedScalarArray avoids a detached result and cloned call for every
// inline builtin scalar. Other lists retain the general decoder, including its
// validation and errors for malformed payloads.
func decodePersistedScalarArray(dag *Server, items []PersistedResultEnvelope, frame *ResultCall, elem Typed) (Typed, bool) {
	typ := frame.Type.Elem
	if len(items) == 0 || !typ.NonNull || typ.Elem != nil || !persistedBuiltinScalarName(typ.NamedType) {
		return nil, false
	}
	var decoder InputDecoder
	if dag != nil {
		if scalar, ok := dag.ScalarType(typ.NamedType); ok {
			switch scalar.(type) {
			case String, Int, Float, Boolean:
				decoder = scalar
			default:
				return nil, false
			}
		}
	}
	for _, item := range items {
		if item.Version != persistedResultEnvelopeVersion || item.Kind != persistedResultKindScalar || item.TypeName != typ.NamedType ||
			item.ResultID != 0 || item.SessionResourceHandle != "" || item.Imported ||
			len(item.PendingOffers) != 0 || len(item.StoredParts) != 0 || len(item.ObjectJSON) != 0 || len(item.Items) != 0 {
			return nil, false
		}
	}
	values := make([]Typed, len(items))
	for i, item := range items {
		raw, err := DecodeLosslessJSON(item.ScalarJSON)
		if err != nil {
			return nil, false
		}
		var value Typed
		if decoder != nil {
			input, err := decoder.DecodeInput(raw)
			if err != nil {
				return nil, false
			}
			value = input
		} else {
			value, err = decodeBuiltinPersistedScalar(item.TypeName, raw)
			if err != nil {
				return nil, false
			}
		}
		values[i] = value
	}
	return persistedScalarArray{
		DynamicArrayOutput: DynamicArrayOutput{Elem: elem, Values: values},
		frame:              frame.clone(),
	}, true
}
