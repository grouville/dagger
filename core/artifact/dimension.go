// Package artifact defines artifact metadata shared by the engine and CLI.
package artifact

import (
	"fmt"
	"strings"

	"github.com/vektah/gqlparser/v2/ast"
)

// Dimension describes a schema axis, independent of its runtime keys.
type Dimension struct {
	CollectionType string `field:"true" doc:"The schema type name of the collection that supplies this dimension."`
	Identifier     string `field:"true" doc:"Exact GraphQL ParentType.field identifier."`
	Name           string `field:"true" doc:"Short name derived from the author item type."`
	QualifiedName  string `field:"true" doc:"Author parent type and field name, in CLI case."`
	ItemType       string `field:"true" doc:"The author item type name."`
	KeyName        string `field:"true" doc:"The name of the author get function's key argument."`
	KeyDescription string `field:"true" doc:"The description of the author get function's key argument."`
}

func (*Dimension) Type() *ast.Type {
	return &ast.Type{NamedType: "ArtifactDimension", NonNull: true}
}

// Dimensions is the set of dimensions in a selected schema scope.
type Dimensions []*Dimension

// Resolve binds an identifier or alias. Unknown names remain valid selectors
// that match no artifacts.
func (dims Dimensions) Resolve(name string) (string, error) {
	for _, dim := range dims {
		if dim.Identifier == name {
			return name, nil
		}
	}
	var matches []string
	for _, dim := range dims {
		if dim.Name == name || dim.QualifiedName == name {
			matches = append(matches, dim.Identifier)
		}
	}
	switch len(matches) {
	case 0:
		return name, nil
	case 1:
		return matches[0], nil
	default:
		return "", fmt.Errorf("ambiguous dimension %q: use %s", name, strings.Join(matches, " or "))
	}
}

// DisplayName returns the shortest unambiguous name for a dimension.
func (dims Dimensions) DisplayName(dim *Dimension) string {
	for _, alias := range []string{dim.Name, dim.QualifiedName} {
		if id, err := dims.Resolve(alias); err == nil && id == dim.Identifier {
			return alias
		}
	}
	return dim.Identifier
}

// DimensionNameIndex resolves display aliases within one immutable schema scope.
// Building it costs O(number of dimensions); each display-name lookup is O(1).
type DimensionNameIndex struct {
	small       Dimensions
	identifiers map[string]bool
	aliases     map[string]string
	counts      map[string]int
}

func (dims Dimensions) IndexNames() *DimensionNameIndex {
	// Most paths have one or two dimensions. A bounded linear lookup avoids
	// three maps per path while keeping lookup cost independent of large scopes.
	if len(dims) <= 8 {
		return &DimensionNameIndex{small: dims}
	}
	index := &DimensionNameIndex{
		identifiers: make(map[string]bool, len(dims)),
		aliases:     map[string]string{},
		counts:      map[string]int{},
	}
	for _, dim := range dims {
		index.identifiers[dim.Identifier] = true
		index.aliases[dim.Name] = dim.Identifier
		index.counts[dim.Name]++
		// Resolve counts each matching dimension only once.
		if dim.QualifiedName != dim.Name {
			index.aliases[dim.QualifiedName] = dim.Identifier
			index.counts[dim.QualifiedName]++
		}
	}
	return index
}

func (index *DimensionNameIndex) DisplayName(dim *Dimension) string {
	if index.small != nil {
		return index.small.DisplayName(dim)
	}
	for _, alias := range []string{dim.Name, dim.QualifiedName} {
		// Exact identifiers take precedence over aliases, as in Resolve.
		if index.identifiers[alias] {
			if alias == dim.Identifier {
				return alias
			}
		} else if index.counts[alias] == 1 && index.aliases[alias] == dim.Identifier {
			return alias
		} else if index.counts[alias] == 0 && alias == dim.Identifier {
			return alias
		}
	}
	return dim.Identifier
}
