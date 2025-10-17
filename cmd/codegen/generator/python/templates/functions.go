package templates

import (
	"cmp"
	"regexp"
	"slices"
	"sort"
	"strings"
	"text/template"
	"unicode"

	"github.com/dagger/dagger/cmd/codegen/generator"
	"github.com/dagger/dagger/cmd/codegen/introspection"
	"github.com/iancoleman/strcase"
)

func PythonTemplateFuncs(schemaVersion string, cfg generator.Config) template.FuncMap {
	common := generator.NewCommonFunctions(schemaVersion, &FormatTypeFunc{})

	f := pythonTemplateFuncs{
		cfg:           cfg,
		schemaVersion: schemaVersion,
		common:        common,
	}
	return template.FuncMap{
		// Formatting
		"FormatPyName":      f.formatPyName,
		"FormatInputType":   f.formatInputType,  // Python-aware, includes optionals
		"FormatOutputType":  f.formatOutputType, // Python-aware, includes object non-optional rule
		"FormatReturnType":  f.formatReturnType,
		"QueryToClient":     f.queryToClient,
		"IsKeyword":         f.isKeyword,
		"IsReservedBuiltin": f.isReservedBuiltin,

		// Behavior helpers
		"GetRequiredArgs": f.getRequiredArgs,
		"GetOptionalArgs": f.getOptionalArgs,
		"IsListOfObject":  f.common.IsListOfObject,
		"IsListOfEnum":    f.common.IsListOfEnum,
		"ConvertID":       f.common.ConvertID,
		"IsSelfChainable": f.common.IsSelfChainable,
		"GetArrayField":   f.common.GetArrayField,
		"IsExec":          f.isExec,
		"IsLeaf":          f.isLeaf,
		"IsVoid":          f.isVoid,
		"ReturnSelf":      f.returnSelf,
		"ToSingleType":    f.toSingleType,
		"Subtract":        f.subtract,

		// Comments/doc
		"CommentToLines":     f.commentToLines,
		"FormatDeprecation":  f.formatDeprecation,
		"FormatExperimental": f.formatExperimental,

		// Enums
		"SortEnumFields":   f.sortEnumFields,
		"GroupEnumByValue": f.groupEnumByValue,
		"SortInputFields":  f.sortInputFields,

		// Exports
		"ExportedNames": f.exportedNames,
		"HasPrefix":     strings.HasPrefix,
	}
}

func (f pythonTemplateFuncs) subtract(a, b int) int {
	return a - b
}

type pythonTemplateFuncs struct {
	schemaVersion string
	cfg           generator.Config
	common        *generator.CommonFunctions
}

func (f pythonTemplateFuncs) queryToClient(s string) string {
	if s == generator.QueryStructName {
		return generator.QueryStructClientName
	}
	return s
}

func (f pythonTemplateFuncs) formatPyName(s string) string {
	// normalize runs of capitals, e.g., URLPath -> UrlPath
	s = normalizeAcronyms(s)
	s = strcase.ToSnake(s)
	if f.isKeyword(s) || f.isReservedBuiltin(s) {
		s += "_"
	}
	return s
}

func normalizeAcronyms(s string) string {
	if s == "" {
		return s
	}

	runes := []rune(s)
	var b strings.Builder
	b.Grow(len(s))

	for i := 0; i < len(runes); {
		r := runes[i]
		if isUpperOrDigit(r) {
			j := i
			for j < len(runes) && isUpperOrDigit(runes[j]) {
				j++
			}

			nextIsAcronymBoundary := j == len(runes)
			if !nextIsAcronymBoundary {
				nextIsAcronymBoundary = isUpperOrDigit(runes[j])
			}

			chunk := runes[i:j]
			if nextIsAcronymBoundary {
				chunk = toTitleRun(chunk)
			}
			b.WriteString(string(chunk))
			i = j
			continue
		}

		b.WriteRune(r)
		i++
	}

	return b.String()
}

func toTitleRun(rs []rune) []rune {
	if len(rs) == 0 {
		return rs
	}

	out := make([]rune, len(rs))
	for i, r := range rs {
		out[i] = unicode.ToLower(r)
	}
	out[0] = unicode.ToUpper(out[0])
	return out
}

func isUpperOrDigit(r rune) bool {
	return unicode.IsUpper(r) || unicode.IsDigit(r)
}

func (f pythonTemplateFuncs) isKeyword(s string) bool {
	py := map[string]struct{}{
		"false": {}, "none": {}, "true": {},
		"and": {}, "as": {}, "assert": {}, "async": {}, "await": {},
		"break": {}, "class": {}, "continue": {}, "def": {}, "del": {},
		"elif": {}, "else": {}, "except": {}, "finally": {}, "for": {},
		"from": {}, "global": {}, "if": {}, "import": {}, "in": {},
		"is": {}, "lambda": {}, "nonlocal": {}, "not": {}, "or": {},
		"pass": {}, "raise": {}, "return": {}, "try": {}, "while": {},
		"with": {}, "yield": {},
	}
	_, ok := py[strings.ToLower(s)]
	return ok
}

func (f pythonTemplateFuncs) isReservedBuiltin(s string) bool {
	// avoid overshadowing as Python names in parameters
	switch s {
	case "str", "int", "float", "bool", "list", "type":
		return true
	}
	return false
}

// Python-aware FormatInputType: include optionals (` | None`).
func (f pythonTemplateFuncs) formatInputType(t *introspection.TypeRef, scopes ...string) (string, error) {
	base, err := f.common.FormatInputType(t, strings.Join(scopes, ""))
	if err != nil {
		return "", err
	}
	if t.IsOptional() {
		// Wrap entire annotation, not only tail-most type.
		return base + " | None", nil
	}
	return base, nil
}

// Python-aware FormatOutputType:
// - If the output is a non-leaf object, force non-optional (to keep chaining).
// - Otherwise, include optionals for true leafs.
func (f pythonTemplateFuncs) formatOutputType(t *introspection.TypeRef, scopes ...string) (string, error) {
	base, err := f.common.FormatOutputType(t, strings.Join(scopes, ""))
	if err != nil {
		return "", err
	}
	inner := f.common.InnerType(t)
	// Leaf => allow optional; Non-leaf object => treat as non-optional
	if inner.IsObject() {
		return base, nil
	}
	if t.IsOptional() {
		return base + " | None", nil
	}
	return base, nil
}

func (f pythonTemplateFuncs) formatReturnType(field introspection.Field, scopes ...string) (string, error) {
	return f.common.FormatReturnType(field, strings.Join(scopes, ""))
}

func (f pythonTemplateFuncs) getRequiredArgs(values introspection.InputValues) introspection.InputValues {
	return typescriptLikeSplit(values).required
}

func (f pythonTemplateFuncs) getOptionalArgs(values introspection.InputValues) introspection.InputValues {
	return typescriptLikeSplit(values).optional
}

func (f pythonTemplateFuncs) sortInputFields(values introspection.InputValues) introspection.InputValues {
	clone := slices.Clone(values)
	slices.SortStableFunc(clone, func(a, b introspection.InputValue) int {
		return cmp.Compare(a.Name, b.Name)
	})
	return clone
}

type splitArgs struct{ required, optional introspection.InputValues }

func typescriptLikeSplit(values introspection.InputValues) splitArgs {
	for i, v := range values {
		if !v.IsOptional() {
			continue
		}
		return splitArgs{required: values[:i], optional: values[i:]}
	}
	return splitArgs{required: values, optional: nil}
}

func (f pythonTemplateFuncs) isLeaf(t *introspection.TypeRef) bool {
	inner := f.common.InnerType(t)
	return inner.IsScalar() || inner.IsEnum()
}

func (f pythonTemplateFuncs) isExec(t *introspection.Field) bool {
	// exec when the field is leaf or a list
	return f.isLeaf(t.TypeRef) || t.TypeRef.IsList()
}

func (f pythonTemplateFuncs) isVoid(t *introspection.Field) bool {
	inner := f.common.InnerType(t.TypeRef)
	return inner.IsScalar() && inner.Name == "Void"
}

func (f pythonTemplateFuncs) returnSelf(field introspection.Field) bool {
	// true if formatted return type equals parent object after Query->Client mapping
	objName, err := f.common.ObjectName(field.TypeRef)
	if err != nil {
		return false
	}
	parent := f.queryToClient(field.ParentObject.Name)
	return objName == parent
}

func (f pythonTemplateFuncs) toSingleType(value string) string {
	// "Foo[]" => "Foo"
	if strings.HasSuffix(value, "[]") {
		return value[:len(value)-2]
	}
	return value
}

func (f pythonTemplateFuncs) commentToLines(s string) []string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n")
}

func (f pythonTemplateFuncs) formatDeprecation(s string) []string {
	// Replace `foo_bar` with snake-case name; keep message compact.
	r := regexp.MustCompile("`[a-zA-Z0-9_]+`")
	s = r.ReplaceAllStringFunc(s, func(m string) string {
		name := strings.Trim(m, "`")
		// return name
		return f.formatPyName(name)
	})
	return f.commentToLines("Deprecated: " + s)
}

func (f pythonTemplateFuncs) formatExperimental(_ string) []string {
	return f.commentToLines("Experimental API (subject to change).")
}

func (f pythonTemplateFuncs) sortEnumFields(s []introspection.EnumValue) []introspection.EnumValue {
	cp := slices.Clone(s)
	slices.SortStableFunc(cp, func(x, y introspection.EnumValue) int {
		return cmp.Compare(x.Name, y.Name)
	})
	// collapse exact duplicates by name
	cp = slices.CompactFunc(cp, func(a, b introspection.EnumValue) bool {
		return a.Name == b.Name && a.Directives.EnumValue() == b.Directives.EnumValue()
	})
	return cp
}

func (f pythonTemplateFuncs) groupEnumByValue(s []introspection.EnumValue) [][]introspection.EnumValue {
	m := map[string][]introspection.EnumValue{}
	for _, v := range s {
		value := v.Directives.EnumValue()
		if value == "" {
			value = v.Name
		}
		found := false
		for _, e := range m[value] {
			if e.Name == v.Name {
				found = true
				break
			}
		}
		if !found {
			m[value] = append(m[value], v)
		}
	}
	var result [][]introspection.EnumValue
	for _, v := range s {
		value := v.Directives.EnumValue()
		if value == "" {
			value = v.Name
		}
		if xs, ok := m[value]; ok {
			result = append(result, xs)
			delete(m, value)
		}
	}
	return result
}

func (f pythonTemplateFuncs) exportedNames(types []*introspection.Type) []string {
	names := make([]string, 0, len(types)+1)
	for _, t := range types {
		switch t.Kind {
		case introspection.TypeKindScalar:
			// Built-in scalars (String, Int...) are not exported; custom are classes.
			switch introspection.Scalar(t.Name) {
			case introspection.ScalarString, introspection.ScalarInt, introspection.ScalarFloat, introspection.ScalarBoolean:
				// skip
			default:
				names = append(names, t.Name)
			}
		case introspection.TypeKindEnum:
			if !strings.HasPrefix(t.Name, "_") {
				names = append(names, t.Name)
			}
		case introspection.TypeKindInputObject:
			names = append(names, t.Name)
		case introspection.TypeKindObject:
			if t.Name == generator.QueryStructName {
				names = append(names, generator.QueryStructClientName)
			} else {
				names = append(names, t.Name)
			}
		}
	}
	names = append(names, "dag")
	sort.Strings(names)
	return names
}
