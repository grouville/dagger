{{- define "call_args" -}}
  {{- $required := RequiredArgs . -}}
  {{- $optional := OptionalArgs . -}}
  {{- if or $required $optional }}
_args = [
  {{- range $required }}
  {{ .ArgExpr }},
  {{- end -}}
  {{- range $optional }}
  {{ .ArgExpr }},
  {{- end }}
]
  {{- else }}
_args: list[Arg] = []
  {{- end }}
{{- end -}}
