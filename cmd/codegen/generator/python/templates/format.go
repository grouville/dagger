package templates

import (
	"strings"

	"github.com/dagger/dagger/cmd/codegen/generator"
)

// FormatTypeFunc maps GraphQL kinds to Python type fragments.
type FormatTypeFunc struct {
	scope string
}

func (f *FormatTypeFunc) WithScope(scope string) generator.FormatTypeFuncs {
	if scope != "" {
		scope += "."
	}
	cp := *f
	cp.scope = scope
	return &cp
}

func (f *FormatTypeFunc) FormatKindList(repr string) string {
	// Python: list[repr]
	return "list[" + repr + "]"
}

func (f *FormatTypeFunc) FormatKindScalarString(repr string) string {
	return repr + "str"
}
func (f *FormatTypeFunc) FormatKindScalarInt(repr string) string {
	return repr + "int"
}
func (f *FormatTypeFunc) FormatKindScalarFloat(repr string) string {
	return repr + "float"
}
func (f *FormatTypeFunc) FormatKindScalarBoolean(repr string) string {
	return repr + "bool"
}

func (f *FormatTypeFunc) FormatKindScalarDefault(repr, refName string, input bool) string {
	// Convert FooID -> Foo on input positions (matches existing behavior).
	if obj, rest, ok := strings.Cut(refName, "ID"); input && ok && rest == "" {
		return repr + f.scope + obj
	}
	// Built-in extended scalars your Python SDK understands.
	switch refName {
	case "Date":
		return repr + "date"
	case "DateTime":
		return repr + "datetime"
	case "Time":
		return repr + "time"
	case "Decimal":
		return repr + "Decimal"
	default:
		// Custom scalars are classes in the generated module.
		return repr + f.scope + refName
	}
}

func (f *FormatTypeFunc) FormatKindObject(repr, refName string, _ bool) string {
	name := refName
	if name == generator.QueryStructName {
		name = generator.QueryStructClientName
	}
	return repr + f.scope + name
}

func (f *FormatTypeFunc) FormatKindInputObject(repr, refName string, _ bool) string {
	return repr + f.scope + refName
}

func (f *FormatTypeFunc) FormatKindEnum(repr, refName string) string {
	return repr + f.scope + refName
}
