{{- define "call_args" -}}
  {{- $required := GetRequiredArgs .Args -}}
  {{- $optionals := GetOptionalArgs .Args -}}
  {{- if or $required $optionals }}
_args = [
  {{- range $required }}
  Arg("{{ .Name }}", {{ .Name | FormatPyName }}),
  {{- end -}}
  {{- range $optionals }}
  {{- /* Optional args set None by default; Arg will omit when None (upstream behavior). */ -}}
  Arg("{{ .Name }}", {{ .Name | FormatPyName }}),
  {{- end }}
]
  {{- else }}
_args: list[Arg] = []
  {{- end }}
{{- end -}}