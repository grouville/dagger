{{- define "args" -}}
  {{- $required := GetRequiredArgs .Args -}}
  {{- $optionals := GetOptionalArgs .Args -}}

  {{- range $i, $arg := $required -}}
    {{- if $i }}, {{ end -}}
    {{ $arg.Name | FormatPyName }}: {{ $arg.TypeRef | FormatInputType }}
  {{- end -}}

  {{- if $optionals -}}
    {{- if $required }}, *{{ else }}*{{ end -}}
    {{- range $opt := $optionals -}}
      , {{ $opt.Name | FormatPyName }}: {{ $opt.TypeRef | FormatInputType }} = None
    {{- end -}}
  {{- end -}}
{{- end -}}
