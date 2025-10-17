{{- define "types" -}}
  {{- range .Types }}
    {{- template "type" . }}
  {{- end -}}
{{- end -}}

{{- define "type" -}}
  {{- if and (eq .Kind "SCALAR") (or (ne .Name "String") (ne .Name "Int")) -}}
    {{- if and (ne .Name "String") (ne .Name "Int") (ne .Name "Float") (ne .Name "Boolean") -}}
      {{- if .Description }}
"""{{- range CommentToLines .Description }}
{{ . }}{{ end -}}
"""
      {{- end }}
class {{ .Name }}(Scalar):
    ...
{{ "" }}
    {{- end -}}
  {{- end -}}

  {{- if eq .Kind "ENUM" -}}
    {{- if .Description }}
"""{{- range CommentToLines .Description }}
{{ . }}{{ end -}}
"""
    {{- end }}
class {{ .Name }}(Enum):
  {{- range $group := SortEnumFields .EnumValues | GroupEnumByValue }}
    {{- $first := index $group 0 }}
    {{- $val := or $first.Directives.EnumValue $first.Name }}
  {{- range $ev := $group }}
    {{ $ev.Name }} = {{ printf "%q" $val }}
  {{- end }}
  {{- end }}
{{ "" }}
  {{- end -}}

  {{- if eq .Kind "INPUT_OBJECT" -}}
@typecheck
@dataclass(slots=True)
class {{ .Name }}(Input):
  {{- range $i, $field := (SortInputFields .InputFields) }}
    {{- if $field.Description }}
    """{{- range CommentToLines $field.Description }}
    {{ . }}{{ end -}}
    """
    {{- end }}
    {{ $field.Name | FormatPyName }}: {{ $field.TypeRef | FormatInputType }}
  {{- end }}
{{ "" }}
  {{- end -}}
{{- end -}}
