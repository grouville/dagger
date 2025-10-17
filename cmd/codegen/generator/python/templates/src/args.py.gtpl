{{- define "args" -}}
  {{- $required := RequiredArgs . -}}
  {{- $optional := OptionalArgs . -}}

  {{- range $i, $arg := $required -}}
    {{- if $i }}, {{ end -}}
    {{ $arg.Param }}
  {{- end -}}

  {{- if $optional -}}
    {{- if $required }}, *{{ else }}*{{ end -}}
    {{- range $opt := $optional -}}
      , {{ $opt.ParamWithDefault }}
    {{- end -}}
  {{- end -}}
{{- end -}}
