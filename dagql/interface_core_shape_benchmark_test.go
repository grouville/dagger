package dagql

import (
	"fmt"
	"testing"
)

// Match core's few shared interfaces against objects with many unrelated fields.
// Each iteration includes constructing the schema, as in the other fixtures.
func BenchmarkInterfaceCoreShape(b *testing.B) {
	for _, count := range []int{128, 512} {
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				srv := candidateIndexServer()
				node := NewInterface("Node", "")
				node.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "id", Type: AnyID{}}})
				syncer := NewInterface("Syncer", "")
				syncer.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "id", Type: AnyID{}}})
				syncer.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "sync", Type: AnyID{}}})
				exportable := NewInterface("Exportable", "")
				exportable.AddField(InterfaceFieldSpec{FieldSpec: FieldSpec{Name: "id", Type: AnyID{}}})
				export := FieldSpec{Name: "export", Type: String(""), Args: NewInputSpecs(InputSpec{Name: "path", Type: String("")})}
				exportable.AddField(InterfaceFieldSpec{FieldSpec: export})
				srv.interfaces["Node"] = node
				srv.interfaces["Syncer"] = syncer
				srv.interfaces["Exportable"] = exportable
				for i := range count {
					name := fmt.Sprintf("CoreType%d", i)
					class := NewClass(srv, ClassOpts[candidateIndexType]{Typed: candidateIndexType(name), NoIDs: true})
					class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "id", Type: AnyID{}}})
					for j := range 64 {
						class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: fmt.Sprintf("extra%d", j), Type: String("")}})
					}
					if i%8 == 0 {
						class.Install(Field[candidateIndexType]{Spec: &FieldSpec{Name: "sync", Type: AnyID{}}})
					}
					if i%16 == 0 {
						class.Install(Field[candidateIndexType]{Spec: &export})
					}
					class.ImplementInterfaceUnchecked(node)
					srv.objects[name] = class
				}
				srv.reconcileInterfaceImplsLocked("")
				if !syncer.HasImplementor("CoreType0") || !exportable.HasImplementor("CoreType0") || syncer.HasImplementor("CoreType1") {
					b.Fatal("core interface matches changed")
				}
			}
		})
	}
}
