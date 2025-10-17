{{ define "types" }}
{{ range $index, $type := .Types }}{{ if gt $index 0 }}

{{ end }}{{ template "type" $type }}{{ end }}
{{ end }}

{{ define "type" }}
{{ if and (eq .Kind "SCALAR") (ne .Name "String") (ne .Name "Int") (ne .Name "Float") (ne .Name "Boolean") }}
class {{ .Name }}(Scalar):
{{ if .Description }}    """{{- $lines := CommentToLines .Description -}}{{- range $i, $line := $lines }}{{ if gt $i 0 }}
    {{ end }}{{ $line }}{{ end }}"""
{{ else }}    ...
{{ end }}

{{ else if eq .Kind "ENUM" }}
class {{ .Name }}(Enum):
{{ if .Description }}    """{{- $lines := CommentToLines .Description -}}{{- range $i, $line := $lines }}{{ if gt $i 0 }}
    {{ end }}{{ $line }}{{ end }}"""
{{ end }}{{ range $group := SortEnumFields .EnumValues | GroupEnumByValue }}
{{ $first := index $group 0 }}
{{ $val := or $first.Directives.EnumValue $first.Name }}{{ range $ev := $group }}
    {{ $ev.Name }} = {{ printf "%q" $val }}
{{ end }}
{{ end }}

{{ else if eq .Kind "INPUT_OBJECT" }}
@typecheck
@dataclass(slots=True)
class {{ .Name }}(Input):
{{ if .Description }}    """{{- $lines := CommentToLines .Description -}}{{- range $i, $line := $lines }}{{ if gt $i 0 }}
    {{ end }}{{ $line }}{{ end }}"""
{{ end }}{{ range $field := SortInputFields .InputFields }}
{{ if $field.Description }}    """{{- $lines := CommentToLines $field.Description -}}{{- range $i, $line := $lines }}{{ if gt $i 0 }}
    {{ end }}{{ $line }}{{ end }}"""
{{ end }}    {{ $field.Name | FormatPyName }}: {{ $field.TypeRef | FormatInputType }}{{ if $field.TypeRef.IsOptional }} = None{{ end }}
{{ end }}

{{ end }}
{{ end }}
