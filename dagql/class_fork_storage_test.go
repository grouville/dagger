package dagql

import (
	"fmt"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestClassForkStorageIsolation(t *testing.T) {
	srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
	parent := NewClass[*reflectedAccessorTestObject](srv)
	parent.Extend(FieldSpec{Name: "original", Type: String("")}, nil)
	object, err := parent.ForkObjectType(srv)
	require.NoError(t, err)
	fork := object.(Class[*reflectedAccessorTestObject])
	valueCopy := fork
	valueCopy.Extend(FieldSpec{Name: "forkOnly", Type: String("")}, nil)
	parent.Extend(FieldSpec{Name: "parentOnly", Type: String("")}, nil)
	_, ok := fork.Field("forkOnly", "")
	require.True(t, ok)
	_, ok = parent.Field("forkOnly", "")
	require.False(t, ok)
	_, ok = fork.Field("parentOnly", "")
	require.False(t, ok)
	// A fork of a fork keeps its own view after either earlier branch changes.
	childObject, err := fork.ForkObjectType(srv)
	require.NoError(t, err)
	child := childObject.(Class[*reflectedAccessorTestObject])
	fork.Install(Field[*reflectedAccessorTestObject]{Spec: &FieldSpec{Name: "later", Type: String("")}})
	child.Extend(FieldSpec{Name: "childOnly", Type: String("")}, nil)
	_, ok = child.Field("later", "")
	require.False(t, ok)
	_, ok = fork.Field("childOnly", "")
	require.False(t, ok)
	// Adding interface conformance to one branch must not alter another.
	iface := NewInterface("ForkOnlyInterface", "")
	child.ImplementInterfaceUnchecked(iface)
	require.Empty(t, fork.Interfaces())
	require.Empty(t, parent.Interfaces())
	require.Len(t, child.Interfaces(), 1)
}

func TestClassForkStorageConcurrentMutation(t *testing.T) {
	srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
	parent := NewClass[*reflectedAccessorTestObject](srv)
	var group sync.WaitGroup
	for worker := range 8 {
		group.Go(func() {
			for iteration := range 30 {
				object, err := parent.ForkObjectType(srv)
				if err != nil {
					t.Error(err)
					return
				}
				fork := object.(Class[*reflectedAccessorTestObject])
				name := fmt.Sprintf("worker%d_%d", worker, iteration)
				fork.Extend(FieldSpec{Name: name, Type: String("")}, nil)
				if _, ok := parent.Field(name, ""); ok {
					t.Errorf("fork field %q escaped", name)
				}
				parent.Extend(FieldSpec{Name: fmt.Sprintf("parent%d_%d", worker, iteration), Type: String("")}, nil)
			}
		})
	}
	group.Wait()
}


var classForkStorageSink ObjectType

func BenchmarkClassForkStorage(b *testing.B) {
	srv := newDagqlServerForTest(b, &reflectedAccessorTestObject{})
	for _, count := range []int{1, 16, 128} {
		class := NewClass[*reflectedAccessorTestObject](srv)
		for i := range count {
			class.Extend(FieldSpec{Name: fmt.Sprint("field", i), Type: String("")}, nil)
		}
		for _, mutate := range []bool{false, true} {
			b.Run(fmt.Sprintf("fields%d/mutate%t", count, mutate), func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					fork, err := class.ForkObjectType(srv)
					if err != nil {
						b.Fatal(err)
					}
					if mutate {
						fork.Extend(FieldSpec{Name: "changed", Type: String("")}, nil)
					}
					classForkStorageSink = fork
				}
			})
		}
	}
}
