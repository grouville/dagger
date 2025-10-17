{{- define "default" -}}
dag = Client()
"""The global client instance."""

__all__ = [
  {{- $names := ExportedNames .Types -}}
  {{- range $i, $n := $names -}}
  {{- if $i }},{{ end }}
  "{{ $n }}"
  {{- end }}
]
{{- end -}}