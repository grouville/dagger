{{- define "objects" -}}
  {{- range .Types }}
    {{- if eq .Kind "OBJECT" }}
      {{- if HasPrefix .Name "_" -}}
        {{- /* ignore internal types */ -}}
      {{- else -}}
        {{- template "object" . -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}

{{- define "object" -}}
  {{- $cls := .Name | QueryToClient }}
  {{- if .Description }}
"""{{- range CommentToLines .Description }}
{{ . }}{{ end -}}
"""
  {{- end }}
@typecheck
class {{ $cls }}({{ if eq .Name "Query" }}Root{{ else }}Type{{ end }}):
  {{- range .Fields }}
    {{- if or (eq .TypeRef.Kind "") (eq .Name "") -}}
      {{- /* skip invalid field */ -}}
    {{- else -}}
      {{- if (IsLeaf .TypeRef) }}{{ template "method_solve" . }}{{- else }}{{ template "method" . }}{{- end }}
    {{- end -}}
  {{- end }}

  {{- if . | IsSelfChainable }}
  def with_(self, cb: Callable[[ "{{ $cls }}" ], "{{ $cls }}" ]) -> "{{ $cls }}":
      """Call the provided callable with current {{ $cls }}.

      This is useful for reusability and readability by not breaking the calling chain.
      """
      return cb(self)
  {{- end }}
{{- end -}}