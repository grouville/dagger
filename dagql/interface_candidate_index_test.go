package dagql

import (
	"fmt"
	"sync"
	"testing"

	"github.com/dagger/dagger/dagql/call"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type candidateIndexType string

func (name candidateIndexType) Type() *ast.Type {
	return &ast.Type{NamedType: string(name), NonNull: true}
}

func candidateIndexServer() *Server {
	return &Server{objects: map[string]ObjectType{}, interfaces: map[string]*Interface{}, installLock: new(sync.RWMutex), schemaLock: new(sync.Mutex)}
}

func TestInterfaceCandidatesPreserveDeclaredEvidence(t *testing.T) {
	srv := candidateIndexServer()
	leaf := NewInterface("Leaf", "")
	leaf.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "missing", Type: String("")}})
	outer := NewInterface("Outer", "")
	outer.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "child", Type: candidateIndexType("Leaf")}})
	child := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("Child"), NoIDs: true})
	child.ImplementInterfaceUnchecked(leaf)
	parent := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("Parent"), NoIDs: true})
	parent.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "child", Type: candidateIndexType("Child")}})
	srv.interfaces["Leaf"] = leaf
	srv.interfaces["Outer"] = outer
	srv.objects["Child"] = child
	srv.objects["Parent"] = parent
	srv.reconcileInterfaceImplsLocked("")
	require.True(t, outer.HasImplementor("Parent"), "declared relationships remain evidence even when required fields are absent")
}

func TestInterfaceCandidatesPreserveEmptyInterface(t *testing.T) {
	srv := candidateIndexServer()
	iface := NewInterface("Empty", "")
	class := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("NoFields"), NoIDs: true})
	srv.interfaces["Empty"] = iface
	srv.objects["NoFields"] = class
	srv.reconcileInterfaceImplsLocked("")
	require.True(t, iface.HasImplementor("NoFields"))
}

func TestInterfaceCandidatesPropagateMissingRecursiveEvidence(t *testing.T) {
	for _, present := range []bool{false, true} {
		t.Run(fmt.Sprint(present), func(t *testing.T) {
			srv := candidateIndexServer()
			left := NewInterface("Left", "")
			right := NewInterface("Right", "")
			left.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "next", Type: candidateIndexType("Right")}})
			right.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "next", Type: candidateIndexType("Left")}})
			right.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "marker", Type: String("")}})
			a := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("A"), NoIDs: true})
			b := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("B"), NoIDs: true})
			a.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "next", Type: candidateIndexType("B")}})
			b.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "next", Type: candidateIndexType("A")}})
			if present {
				b.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "marker", Type: String("")}})
			}
			srv.interfaces["Left"] = left
			srv.interfaces["Right"] = right
			srv.objects["A"] = a
			srv.objects["B"] = b
			srv.reconcileInterfaceImplsLocked("")
			require.Equal(t, present, left.HasImplementor("A"))
			require.Equal(t, present, right.HasImplementor("B"))
		})
	}
}

type countedCandidateClass struct {
	Class[candidateIndexType]
	checks *int
}

func (c countedCandidateClass) FieldSpec(name string, view call.View) (FieldSpec, bool) {
	*c.checks++
	return c.Class.FieldSpec(name, view)
}

func TestInterfaceCandidatesAvoidUnrelatedFieldProbes(t *testing.T) {
	const count = 64
	srv := candidateIndexServer()
	checks := 0
	for i := range count {
		field := fmt.Sprintf("only%d", i)
		name := fmt.Sprintf("Object%d", i)
		ifaceName := fmt.Sprintf("Interface%d", i)
		iface := NewInterface(ifaceName, "")
		iface.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: field, Type: String("")}})
		class := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType(name), NoIDs: true})
		class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: field, Type: String("")}})
		srv.interfaces[ifaceName] = iface
		srv.objects[name] = countedCandidateClass{class, &checks}
	}
	srv.reconcileInterfaceImplsLocked("")
	for i := range count {
		require.True(t, srv.interfaces[fmt.Sprintf("Interface%d", i)].HasImplementor(fmt.Sprintf("Object%d", i)))
	}
	t.Logf("field probes: %d", checks)
	require.LessOrEqual(t, checks, 2*count, "unrelated object/interface pairs should not require compatibility probes")
}

// A field-rich class should not copy its entire field table to check two names.
type fieldRichCandidateClass struct {
	Class[candidateIndexType]
	snapshots *int
}

func (c fieldRichCandidateClass) FieldSpecs(view call.View) []FieldSpec {
	*c.snapshots++
	return c.Class.FieldSpecs(view)
}
func TestInterfaceCandidatesAvoidCopyingUnrelatedFields(t *testing.T) {
	srv := candidateIndexServer()
	snapshots := 0
	present := NewInterface("Present", "")
	absent := NewInterface("Absent", "")
	present.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "present", Type: String("")}})
	absent.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "absent", Type: String("")}})
	class := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType("FieldRich"), NoIDs: true})
	for i := range 64 {
		class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: fmt.Sprintf("extra%d", i), Type: String("")}})
	}
	class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "present", Type: String("")}})
	srv.objects["FieldRich"] = fieldRichCandidateClass{class, &snapshots}
	srv.interfaces["Present"] = present
	srv.interfaces["Absent"] = absent
	srv.reconcileInterfaceImplsLocked("")
	require.True(t, present.HasImplementor("FieldRich"))
	require.False(t, absent.HasImplementor("FieldRich"))
	require.Zero(t, snapshots, "a few required names should not copy the whole field table")
}
