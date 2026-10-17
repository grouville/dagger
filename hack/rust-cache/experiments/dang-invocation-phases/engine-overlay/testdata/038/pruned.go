package dagql

import (
	"maps"
	"slices"

	"github.com/dagger/dagger/dagql/call"
)

// Reconciliation only removes candidates. A type missing a required field
// cannot become compatible when other candidate relationships are removed.
// Exclude those pairs before building the graph, while retaining declared facts.
func (s *Server) reconcileInterfaceImplsPruned(view call.View) {
	if len(s.interfaces) == 0 {
		return
	}

	objects := slices.Sorted(maps.Keys(s.objects))
	interfaceNames := slices.Sorted(maps.Keys(s.interfaces))
	type requiredInterface struct {
		name   string
		typ    *Interface
		fields []FieldSpec
		loaded bool
	}
	interfaces := make([]requiredInterface, len(interfaceNames))
	for i, name := range interfaceNames {
		interfaces[i] = requiredInterface{name: name, typ: s.interfaces[name]}
	}
	fieldsFor := func(i int) []FieldSpec {
		entry := &interfaces[i]
		if !entry.loaded {
			entry.fields = entry.typ.FieldSpecs(view)
			entry.loaded = true
		}
		return entry.fields
	}

	rels := interfaceRelationSet{}
	permanent := interfaceRelationSet{}
	for _, name := range objects {
		if obj, ok := s.objects[name].(objectTypeWithInterfaces); ok {
			for _, iface := range obj.Interfaces() {
				if iface == nil {
					continue
				}
				if _, installed := s.interfaces[iface.TypeName()]; installed {
					rels.add(name, iface.TypeName())
					permanent.add(name, iface.TypeName())
				}
			}
		}
	}
	for _, entry := range interfaces {
		for name := range entry.typ.Interfaces() {
			if _, installed := s.interfaces[name]; installed {
				rels.add(entry.name, name)
				permanent.add(entry.name, name)
			}
		}
	}

	type objectCandidate struct {
		name  string
		obj   ObjectType
		iface int
	}
	type interfaceCandidate struct {
		name  string
		typ   *Interface
		iface int
	}
	var objectCandidates []objectCandidate
	var interfaceCandidates []interfaceCandidate
	for _, name := range objects {
		obj := s.objects[name]
		if _, ok := obj.(InterfaceImplementor); !ok {
			continue
		}
		for i, iface := range interfaces {
			if permanent.has(name, iface.name) || !hasInterfaceFieldNames(fieldsFor(i), obj.FieldSpec, view) {
				continue
			}
			rels.add(name, iface.name)
			objectCandidates = append(objectCandidates, objectCandidate{name, obj, i})
		}
	}
	for _, entry := range interfaces {
		for i, iface := range interfaces {
			if entry.name == iface.name || permanent.has(entry.name, iface.name) || !hasInterfaceFieldNames(fieldsFor(i), entry.typ.FieldSpec, view) {
				continue
			}
			rels.add(entry.name, iface.name)
			interfaceCandidates = append(interfaceCandidates, interfaceCandidate{entry.name, entry.typ, i})
		}
	}

	// Keep the same sorted pruning order and greatest fixed point, revisiting
	// only surviving candidates. Each removal can invalidate a recursive pair.
	checker := func(name, iface string) bool { return rels.has(name, iface) }
	changed := true
	for changed {
		changed = false
		keptObjects := objectCandidates[:0]
		for _, candidate := range objectCandidates {
			if prunedSatisfiesFields(fieldsFor(candidate.iface), candidate.obj.FieldSpec, view, checker) {
				keptObjects = append(keptObjects, candidate)
			} else {
				rels.del(candidate.name, interfaces[candidate.iface].name)
				changed = true
			}
		}
		objectCandidates = keptObjects
		keptInterfaces := interfaceCandidates[:0]
		for _, candidate := range interfaceCandidates {
			if prunedSatisfiesFields(fieldsFor(candidate.iface), candidate.typ.FieldSpec, view, checker) {
				keptInterfaces = append(keptInterfaces, candidate)
			} else {
				rels.del(candidate.name, interfaces[candidate.iface].name)
				changed = true
			}
		}
		interfaceCandidates = keptInterfaces
	}

	for _, candidate := range objectCandidates {
		iface := interfaces[candidate.iface]
		if !objectTypeHasInterface(candidate.obj, iface.name) {
			candidate.obj.(InterfaceImplementor).ImplementInterfaceUnchecked(iface.typ)
		}
	}
	for _, candidate := range interfaceCandidates {
		iface := interfaces[candidate.iface]
		if _, exists := candidate.typ.Interfaces()[iface.name]; exists {
			continue
		}
		if interfaceImplementsTransitive(iface.typ, candidate.name, nil) {
			continue
		}
		candidate.typ.ImplementInterface(iface.typ)
		s.invalidateSchemaCache()
	}
}

func hasInterfaceFieldNames(fields []FieldSpec, lookup func(string, call.View) (FieldSpec, bool), view call.View) bool {
	for _, field := range fields {
		if _, ok := lookup(field.Name, view); !ok {
			return false
		}
	}
	return true
}

func prunedSatisfiesFields(fields []FieldSpec, lookup func(string, call.View) (FieldSpec, bool), view call.View, checker ImplementsChecker) bool {
	for _, ifaceField := range fields {
		objField, ok := lookup(ifaceField.Name, view)
		if !ok || !typeCompatible(ifaceField.Type.Type(), objField.Type.Type(), checker) || !argsCompatible(ifaceField.Args, objField.Args, view, checker) {
			return false
		}
	}
	return true
}
