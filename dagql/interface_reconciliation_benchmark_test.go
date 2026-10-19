package dagql

import (
	"fmt"
	"sync"
	"testing"

	"github.com/vektah/gqlparser/v2/ast"
)

type reconciliationBenchmarkType string

func (name reconciliationBenchmarkType) Type() *ast.Type {
	return &ast.Type{NamedType: string(name), NonNull: true}
}

// Build a fresh schema on every iteration, including construction in the timer.
// Distinct groups share fields but require different final fields, so matching
// includes both accepted and rejected candidates. The declared case mirrors
// inherited schema relationships that need no new structural checks.
func BenchmarkInterfaceReconciliation(b *testing.B) {
	for _, shape := range []struct {
		objects, interfaces int
		declared            bool
		dense               bool
	}{{1, 1, false, false}, {128, 8, false, false}, {512, 16, false, false}, {128, 8, false, true}, {128, 1, true, false}, {128, 8, true, true}} {
		b.Run(fmt.Sprintf("objects=%d/interfaces=%d/declared=%t/dense=%t", shape.objects, shape.interfaces, shape.declared, shape.dense), func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				srv := &Server{objects: map[string]ObjectType{}, interfaces: map[string]*Interface{}, installLock: new(sync.RWMutex), schemaLock: new(sync.Mutex)}
				for i := range shape.interfaces {
					iface := NewInterface(fmt.Sprintf("I%d", i), "")
					for field := range 8 {
						iface.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: fmt.Sprintf("f%d", field), Type: String("")}})
					}
					group := i % 8
					if shape.dense {
						group = 0
					}
					iface.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: fmt.Sprintf("tag%d", group), Type: String("")}})
					srv.interfaces[iface.TypeName()] = iface
				}
				for i := range shape.objects {
					name := fmt.Sprintf("T%d", i)
					class := NewClass(srv, ClassOpts[reconciliationBenchmarkType]{Typed: reconciliationBenchmarkType(name), NoIDs: true})
					for field := range 8 {
						class.Install(Field[reconciliationBenchmarkType]{Spec: &FieldSpec{Name: fmt.Sprintf("f%d", field), Type: String("")}})
					}
					group := i % min(8, shape.interfaces)
					if shape.dense {
						group = 0
					}
					class.Install(Field[reconciliationBenchmarkType]{Spec: &FieldSpec{Name: fmt.Sprintf("tag%d", group), Type: String("")}})
					if shape.declared {
						for _, iface := range srv.interfaces {
							class.ImplementInterfaceUnchecked(iface)
						}
					}
					srv.objects[name] = class
				}
				srv.installLock.Lock()
				srv.reconcileInterfaceImplsLocked("")
				srv.installLock.Unlock()
				if !srv.interfaces["I0"].HasImplementor("T0") {
					b.Fatal("matching object was not recorded")
				}
			}
		})
	}
}
