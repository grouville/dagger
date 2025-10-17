package templates

import (
	"cmp"
	"fmt"
	"regexp"
	"slices"
	"sort"
	"strconv"
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
		"RequiredArgs":    f.requiredArgs,
		"OptionalArgs":    f.optionalArgs,
		"MethodDocLines":  f.methodDocLines,
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

func (f pythonTemplateFuncs) sortInputFields(values introspection.InputValues) introspection.InputValues {
	clone := slices.Clone(values)
	slices.SortStableFunc(clone, func(a, b introspection.InputValue) int {
		return cmp.Compare(a.Name, b.Name)
	})
	return clone
}

func (f pythonTemplateFuncs) requiredArgs(field *introspection.Field) []MethodArg {
	return f.splitArgs(field).required
}

func (f pythonTemplateFuncs) optionalArgs(field *introspection.Field) []MethodArg {
	return f.splitArgs(field).optional
}

func (f pythonTemplateFuncs) methodDocLines(field *introspection.Field) []string {
	sections := f.methodDocSections(field)
	if len(sections) == 0 {
		return nil
	}
	var lines []string
	for i, section := range sections {
		if len(section) == 0 {
			continue
		}
		if i > 0 {
			lines = append(lines, "")
		}
		lines = append(lines, section...)
	}
	return lines
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

const docWrapWidth = 70

type MethodArg struct {
	GraphQLName      string
	PyName           string
	TypeAnnotation   string
	Description      string
	HasDefault       bool
	DefaultValue     string
	DefaultIsMutable bool
	IsSelf           bool
}

func (a MethodArg) baseType() string {
	if a.IsSelf {
		return "Self"
	}
	return a.TypeAnnotation
}

func (a MethodArg) Param() string {
	return fmt.Sprintf("%s: %s", a.PyName, a.baseType())
}

func (a MethodArg) ParamWithDefault() string {
	typ := a.baseType()
	if a.DefaultIsMutable && !strings.Contains(typ, "| None") {
		typ += " | None"
	}
	param := fmt.Sprintf("%s: %s", a.PyName, typ)
	if a.DefaultIsMutable {
		return param + " = None"
	}
	if a.HasDefault {
		return param + " = " + a.DefaultValue
	}
	return param
}

func (a MethodArg) ArgExpr() string {
	value := a.PyName
	if a.DefaultIsMutable {
		value = fmt.Sprintf("%s if %s is None else %s", a.DefaultValue, a.PyName, a.PyName)
	}
	if a.HasDefault {
		return fmt.Sprintf("Arg(\"%s\", %s, %s)", a.GraphQLName, value, a.DefaultValue)
	}
	return fmt.Sprintf("Arg(\"%s\", %s)", a.GraphQLName, value)
}

func (a MethodArg) DocLines() []string {
	lines := []string{fmt.Sprintf("%s:", a.PyName)}
	desc := strings.TrimSpace(a.Description)
	if desc == "" {
		return lines
	}
	for _, line := range strings.Split(desc, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			lines = append(lines, "")
			continue
		}
		for _, wrapped := range wrapLine(trimmed, docWrapWidth-len("    ")) {
			lines = append(lines, "    "+wrapped)
		}
	}
	return lines
}

func (a MethodArg) HasDescription() bool {
	return strings.TrimSpace(a.Description) != ""
}

type methodArgsSplit struct {
	required []MethodArg
	optional []MethodArg
}

func (f pythonTemplateFuncs) splitArgs(field *introspection.Field) methodArgsSplit {
	args := f.allArgs(field)
	for i, arg := range args {
		if !arg.HasDefault {
			continue
		}
		return methodArgsSplit{required: args[:i], optional: args[i:]}
	}
	return methodArgsSplit{required: args, optional: nil}
}

func (f pythonTemplateFuncs) allArgs(field *introspection.Field) []MethodArg {
	args := make([]MethodArg, 0, len(field.Args))
	for _, input := range field.Args {
		args = append(args, f.buildMethodArg(field, input))
	}
	return args
}

func (f pythonTemplateFuncs) buildMethodArg(field *introspection.Field, input introspection.InputValue) MethodArg {
	typeAnnotation, err := f.formatInputType(input.TypeRef)
	if err != nil {
		panic(err)
	}
	defaultInfo := f.computeDefaultInfo(field, input)
	parentName := ""
	if field.ParentObject != nil {
		parentName = f.queryToClient(field.ParentObject.Name)
	}
	isSelf := parentName != "" && typeAnnotation == parentName
	return MethodArg{
		GraphQLName:      input.Name,
		PyName:           f.formatPyName(input.Name),
		TypeAnnotation:   typeAnnotation,
		Description:      input.Description,
		HasDefault:       defaultInfo.hasDefault,
		DefaultValue:     defaultInfo.literal,
		DefaultIsMutable: defaultInfo.isMutable,
		IsSelf:           isSelf,
	}
}

type defaultInfo struct {
	literal    string
	hasDefault bool
	isMutable  bool
}

func (f pythonTemplateFuncs) computeDefaultInfo(field *introspection.Field, input introspection.InputValue) defaultInfo {
	info := defaultInfo{}
	if input.DefaultValue != nil {
		value, err := parseGraphQLValue(*input.DefaultValue)
		if err != nil {
			panic(err)
		}
		literal, mutable := f.pythonLiteral(input.TypeRef, value)
		info.literal = literal
		info.hasDefault = true
		info.isMutable = mutable
		return info
	}
	if input.TypeRef != nil && input.TypeRef.IsOptional() {
		info.literal = "None"
		info.hasDefault = true
		return info
	}
	return info
}

func (f pythonTemplateFuncs) methodDocSections(field *introspection.Field) [][]string {
	var sections [][]string
	if desc := f.descriptionSection(field.Description); len(desc) > 0 {
		sections = append(sections, desc)
	}
	if field.IsDeprecated {
		reason := strings.TrimSpace(f.rewriteNotice(field.DeprecationReason, ":py:meth:`", "`"))
		if reason != "" {
			section := []string{".. deprecated::"}
			section = append(section, wrapWithIndent(reason, "    ")...)
			sections = append(sections, section)
		}
	}
	if field.Directives.IsExperimental() {
		experimental := strings.TrimSpace(f.rewriteNotice(field.Directives.ExperimentalReason(), ":py:meth:`", "`"))
		if experimental != "" {
			section := []string{".. caution::"}
			section = append(section, wrapWithIndent("Experimental: "+experimental, "    ")...)
			sections = append(sections, section)
		}
	}
	if field.Name == "id" {
		sections = append(sections, []string{
			"Note",
			"----",
			"This is lazily evaluated, no operation is actually run.",
		})
	}
	args := f.allArgs(field)
	if f.hasArgDescription(args) {
		sections = append(sections, f.parametersSection(args))
	}
	if f.isLeaf(field.TypeRef) {
		if returns := f.returnsSection(field); len(returns) > 0 {
			sections = append(sections, returns)
		}
		sections = append(sections, f.raisesSection())
	}
	return sections
}

func (f pythonTemplateFuncs) descriptionSection(desc string) []string {
	desc = strings.TrimSpace(desc)
	if desc == "" {
		return nil
	}
	var lines []string
	for _, line := range strings.Split(desc, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			lines = append(lines, "")
			continue
		}
		lines = append(lines, wrapLine(trimmed, docWrapWidth)...)
	}
	return lines
}

func (f pythonTemplateFuncs) parametersSection(args []MethodArg) []string {
	section := []string{"Parameters", "----------"}
	for _, arg := range args {
		section = append(section, arg.DocLines()...)
	}
	return section
}

func (f pythonTemplateFuncs) returnsSection(field *introspection.Field) []string {
	convertID := f.common.ConvertID(*field)
	if convertID {
		return nil
	}
	desc := strings.TrimSpace(f.returnDescription(field.TypeRef))
	if desc == "" {
		return nil
	}
	retType, err := f.formatReturnType(*field)
	if err != nil {
		panic(err)
	}
	section := []string{"Returns", "-------", retType}
	section = append(section, wrapWithIndent(desc, "    ")...)
	return section
}

func (f pythonTemplateFuncs) raisesSection() []string {
	section := []string{
		"Raises",
		"------",
		"ExecuteTimeoutError",
	}
	for _, line := range wrapWithIndent("If the time to execute the query exceeds the configured timeout.", "    ") {
		section = append(section, line)
	}
	section = append(section, "QueryError")
	section = append(section, "    If the API returns an error.")
	return section
}

func (f pythonTemplateFuncs) hasArgDescription(args []MethodArg) bool {
	for _, arg := range args {
		if arg.HasDescription() {
			return true
		}
	}
	return false
}

func (f pythonTemplateFuncs) rewriteNotice(reason, prefix, suffix string) string {
	reason = strings.TrimSpace(reason)
	if reason == "" {
		return ""
	}
	r := regexp.MustCompile("`[a-zA-Z0-9_]+`")
	return r.ReplaceAllStringFunc(reason, func(m string) string {
		name := strings.Trim(m, "`")
		return prefix + f.formatPyName(name) + suffix
	})
}

func (f pythonTemplateFuncs) returnDescription(ref *introspection.TypeRef) string {
	ref = unwrapNonNull(ref)
	if ref.Kind == introspection.TypeKindList {
		ref = ref.OfType
	}
	schema := generator.GetSchema()
	typeDef := schema.Types.Get(ref.Name)
	if typeDef == nil {
		return ""
	}
	return strings.TrimSpace(typeDef.Description)
}

func wrapLine(text string, width int) []string {
	text = strings.TrimSpace(text)
	if text == "" {
		return nil
	}
	if width <= 0 {
		return []string{text}
	}
	words := strings.Fields(text)
	if len(words) == 0 {
		return nil
	}
	lines := make([]string, 0, len(words))
	current := words[0]
	for _, word := range words[1:] {
		if len(current)+1+len(word) > width {
			lines = append(lines, current)
			current = word
		} else {
			current += " " + word
		}
	}
	lines = append(lines, current)
	return lines
}

func wrapWithIndent(text, indent string) []string {
	text = strings.TrimSpace(text)
	if text == "" {
		return nil
	}
	width := docWrapWidth - len(indent)
	if width <= 0 {
		width = docWrapWidth
	}
	wrapped := wrapLine(text, width)
	if len(wrapped) == 0 {
		return nil
	}
	lines := make([]string, len(wrapped))
	for i, line := range wrapped {
		lines[i] = indent + line
	}
	return lines
}

func unwrapNonNull(ref *introspection.TypeRef) *introspection.TypeRef {
	for ref != nil && ref.Kind == introspection.TypeKindNonNull && ref.OfType != nil {
		ref = ref.OfType
	}
	return ref
}

func (f pythonTemplateFuncs) pythonLiteral(ref *introspection.TypeRef, value interface{}) (string, bool) {
	ref = unwrapNonNull(ref)
	if ref == nil {
		return "None", false
	}
	if value == nil {
		return "None", false
	}
	switch ref.Kind {
	case introspection.TypeKindList:
		listVal, _ := value.([]interface{})
		elemRef := ref.OfType
		items := make([]string, 0, len(listVal))
		for _, item := range listVal {
			lit, _ := f.pythonLiteral(elemRef, item)
			items = append(items, lit)
		}
		return "[" + strings.Join(items, ", ") + "]", true
	case introspection.TypeKindScalar:
		return pythonScalarLiteral(ref.Name, value), false
	case introspection.TypeKindEnum:
		var enumName string
		switch v := value.(type) {
		case enumValue:
			enumName = string(v)
		case string:
			enumName = v
		default:
			enumName = fmt.Sprintf("%v", v)
		}
		return fmt.Sprintf("%s.%s", ref.Name, enumName), false
	case introspection.TypeKindInputObject:
		obj, _ := value.(map[string]interface{})
		if obj == nil {
			return "{}", false
		}
		schema := generator.GetSchema()
		inputType := schema.Types.Get(ref.Name)
		if inputType == nil {
			return "{}", false
		}
		fields := make(map[string]*introspection.TypeRef, len(inputType.InputFields))
		for _, field := range inputType.InputFields {
			field := field
			fields[field.Name] = field.TypeRef
		}
		keys := make([]string, 0, len(obj))
		for key := range obj {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, key := range keys {
			lit, _ := f.pythonLiteral(fields[key], obj[key])
			parts = append(parts, fmt.Sprintf("%s: %s", quotePythonString(key), lit))
		}
		return "{" + strings.Join(parts, ", ") + "}", false
	default:
		return fmt.Sprintf("%v", value), false
	}
}

func pythonScalarLiteral(name string, value interface{}) string {
	switch introspection.Scalar(name) {
	case introspection.ScalarBoolean:
		if value == nil {
			return "None"
		}
		switch v := value.(type) {
		case bool:
			if v {
				return "True"
			}
			return "False"
		case enumValue:
			if strings.EqualFold(string(v), "true") {
				return "True"
			}
			if strings.EqualFold(string(v), "false") {
				return "False"
			}
		case string:
			if strings.EqualFold(v, "true") {
				return "True"
			}
			if strings.EqualFold(v, "false") {
				return "False"
			}
		}
		return "False"
	case introspection.ScalarInt, introspection.ScalarFloat:
		if value == nil {
			return "None"
		}
		switch v := value.(type) {
		case numberValue:
			return string(v)
		case string:
			return v
		default:
			return fmt.Sprintf("%v", v)
		}
	case introspection.ScalarString, introspection.ScalarVoid:
		switch v := value.(type) {
		case string:
			return pythonStringLiteral(v)
		case nil:
			return "None"
		default:
			return pythonStringLiteral(fmt.Sprintf("%v", v))
		}
	default:
		if value == nil {
			return "None"
		}
		switch v := value.(type) {
		case string:
			return pythonStringLiteral(v)
		case numberValue:
			return string(v)
		case bool:
			if v {
				return "True"
			}
			return "False"
		default:
			return fmt.Sprintf("%v", v)
		}
	}
}

func pythonStringLiteral(value string) string {
	return quotePythonString(value)
}

func quotePythonString(value string) string {
	var b strings.Builder
	b.WriteByte('\'')
	for _, r := range value {
		switch r {
		case '\\', '\'':
			b.WriteByte('\\')
			b.WriteRune(r)
		case '\n':
			b.WriteString("\\n")
		case '\r':
			b.WriteString("\\r")
		case '\t':
			b.WriteString("\\t")
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('\'')
	return b.String()
}

type enumValue string
type numberValue string

func parseGraphQLValue(input string) (interface{}, error) {
	p := &valueParser{input: strings.TrimSpace(input)}
	value, err := p.parseValue()
	if err != nil {
		return nil, err
	}
	p.skipWhitespace()
	if !p.done() {
		return nil, fmt.Errorf("unexpected trailing characters in value: %s", p.input[p.pos:])
	}
	return value, nil
}

type valueParser struct {
	input string
	pos   int
}

func (p *valueParser) done() bool {
	return p.pos >= len(p.input)
}

func (p *valueParser) peek() byte {
	if p.done() {
		return 0
	}
	return p.input[p.pos]
}

func (p *valueParser) advance() byte {
	b := p.peek()
	if b != 0 {
		p.pos++
	}
	return b
}

func (p *valueParser) skipWhitespace() {
	for !p.done() {
		switch p.peek() {
		case ' ', '\n', '\r', '\t', '\f', '\v', ',':
			p.pos++
		default:
			return
		}
	}
}

func (p *valueParser) parseValue() (interface{}, error) {
	p.skipWhitespace()
	if p.done() {
		return nil, fmt.Errorf("unexpected end of value")
	}
	switch ch := p.peek(); ch {
	case '"':
		return p.parseString()
	case '[':
		return p.parseList()
	case '{':
		return p.parseObject()
	case 't', 'f':
		return p.parseBool()
	case 'n':
		return p.parseNull()
	case '-', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9':
		return p.parseNumber()
	default:
		return p.parseEnum()
	}
}

func (p *valueParser) parseString() (interface{}, error) {
	start := p.pos
	p.pos++
	for !p.done() {
		c := p.advance()
		if c == '\\' {
			p.pos++
			continue
		}
		if c == '"' {
			raw := p.input[start:p.pos]
			str, err := strconv.Unquote(raw)
			if err != nil {
				return nil, err
			}
			return str, nil
		}
	}
	return nil, fmt.Errorf("unterminated string literal")
}

func (p *valueParser) parseNumber() (interface{}, error) {
	start := p.pos
	if p.peek() == '-' {
		p.pos++
	}
	for !p.done() && isDigit(p.peek()) {
		p.pos++
	}
	if !p.done() && p.peek() == '.' {
		p.pos++
		for !p.done() && isDigit(p.peek()) {
			p.pos++
		}
	}
	if !p.done() && (p.peek() == 'e' || p.peek() == 'E') {
		p.pos++
		if !p.done() && (p.peek() == '+' || p.peek() == '-') {
			p.pos++
		}
		for !p.done() && isDigit(p.peek()) {
			p.pos++
		}
	}
	return numberValue(p.input[start:p.pos]), nil
}

func (p *valueParser) parseEnum() (interface{}, error) {
	name, err := p.parseName()
	if err != nil {
		return nil, err
	}
	return enumValue(name), nil
}

func (p *valueParser) parseName() (string, error) {
	if p.done() {
		return "", fmt.Errorf("unexpected end while reading name")
	}
	if !isNameStart(p.peek()) {
		return "", fmt.Errorf("invalid name start: %c", p.peek())
	}
	start := p.pos
	p.pos++
	for !p.done() && isNameContinue(p.peek()) {
		p.pos++
	}
	return p.input[start:p.pos], nil
}

func (p *valueParser) parseBool() (interface{}, error) {
	if strings.HasPrefix(p.input[p.pos:], "true") {
		p.pos += 4
		return true, nil
	}
	if strings.HasPrefix(p.input[p.pos:], "false") {
		p.pos += 5
		return false, nil
	}
	return nil, fmt.Errorf("invalid boolean literal")
}

func (p *valueParser) parseNull() (interface{}, error) {
	if strings.HasPrefix(p.input[p.pos:], "null") {
		p.pos += 4
		return nil, nil
	}
	return nil, fmt.Errorf("invalid null literal")
}

func (p *valueParser) parseList() (interface{}, error) {
	// assume current char is '['
	p.pos++
	values := []interface{}{}
	for {
		p.skipWhitespace()
		if p.done() {
			return nil, fmt.Errorf("unterminated list literal")
		}
		if p.peek() == ']' {
			p.pos++
			break
		}
		val, err := p.parseValue()
		if err != nil {
			return nil, err
		}
		values = append(values, val)
		p.skipWhitespace()
		if p.peek() == ',' {
			p.pos++
			continue
		}
		if p.peek() == ']' {
			p.pos++
			break
		}
	}
	return values, nil
}

func (p *valueParser) parseObject() (interface{}, error) {
	p.pos++
	result := map[string]interface{}{}
	for {
		p.skipWhitespace()
		if p.done() {
			return nil, fmt.Errorf("unterminated object literal")
		}
		if p.peek() == '}' {
			p.pos++
			break
		}
		name, err := p.parseName()
		if err != nil {
			return nil, err
		}
		p.skipWhitespace()
		if p.peek() != ':' {
			return nil, fmt.Errorf("expected ':' after field name")
		}
		p.pos++
		val, err := p.parseValue()
		if err != nil {
			return nil, err
		}
		result[name] = val
		p.skipWhitespace()
		if p.peek() == ',' {
			p.pos++
			continue
		}
		if p.peek() == '}' {
			p.pos++
			break
		}
	}
	return result, nil
}

func isDigit(b byte) bool {
	return b >= '0' && b <= '9'
}

func isNameStart(b byte) bool {
	return (b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z') || b == '_'
}

func isNameContinue(b byte) bool {
	return isNameStart(b) || isDigit(b)
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
