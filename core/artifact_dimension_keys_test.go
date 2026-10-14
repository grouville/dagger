package core

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestArtifactDimensionKeysAncestors(t *testing.T) {
	type entry struct {
		path, dimensions []string
	}
	for _, tc := range []struct {
		name     string
		entries  []entry
		filters  []ArtifactDimensionFilter
		excluded []string
		want     []string
	}{
		{
			name: "ancestor follows descendant",
			entries: []entry{
				{[]string{"packages", "test"}, []string{"outer"}},
				{[]string{"packages"}, []string{"outer"}},
			},
			want: []string{"Item1"},
		},
		{
			name: "literal path prefixes",
			entries: []entry{
				{[]string{"packages"}, []string{"outer"}},
				{[]string{"packages-other", "test"}, []string{"outer"}},
				{[]string{"packages", "test"}, []string{"outer"}},
			},
			want: []string{"Item0", "Item1"},
		},
		{
			name: "equal paths and dimensions remain distinct",
			entries: []entry{
				{[]string{"packages"}, []string{"outer"}},
				{[]string{"packages"}, []string{"outer"}},
				{[]string{"packages"}, []string{"outer", "inner"}},
			},
			want: []string{"Item0", "Item1"},
		},
		{
			name: "filter requires inner collection",
			entries: []entry{
				{[]string{"packages"}, []string{"outer"}},
				{[]string{"packages", "tests"}, []string{"outer", "inner"}},
				{[]string{"packages", "tests", "check"}, []string{"outer", "inner"}},
			},
			filters: []ArtifactDimensionFilter{{Dimension: "inner", Keys: []string{"x"}}},
			want:    []string{"Item0", "Item1"},
		},
		{
			name: "dimensions must match in order",
			entries: []entry{
				{[]string{"packages"}, []string{"inner", "outer"}},
				{[]string{"packages", "test"}, []string{"outer", "inner"}},
				{[]string{"packages", "other"}, []string{"other", "outer"}},
			},
			want: []string{"Item0", "Item1", "Item2"},
		},
		{
			name: "exclusions can remove keys supplied by ancestors",
			entries: []entry{
				{[]string{"packages"}, []string{"outer"}},
				{[]string{"packages", "test"}, []string{"outer"}},
			},
			excluded: []string{"dag://packages?outer=a"},
			want:     []string{"Item0", "Item1"},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			all := &Artifacts{Selector: ArtifactSelector{Dimensions: tc.filters, ExcludedURIs: tc.excluded}}
			for i, e := range tc.entries {
				var node *ModTreeNode
				for _, dimension := range e.dimensions {
					node = &ModTreeNode{Parent: node, CollectionDimension: &ArtifactDimension{Identifier: dimension, Name: dimension}}
				}
				all.Entries = append(all.Entries, &Artifact{Path: e.path, Node: node, TypeName: fmt.Sprintf("Item%d", i)})
			}
			selected := all.ForDimensionKeys("outer")
			var names []string
			for _, item := range selected.Entries {
				names = append(names, item.TypeName)
			}
			require.Equal(t, tc.want, names)
			require.Equal(t, tc.filters, selected.Selector.Dimensions)
		})
	}
}
