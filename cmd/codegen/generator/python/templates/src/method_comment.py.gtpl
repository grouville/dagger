{{- define "method_comment" -}}
  {{- if or .Description .IsDeprecated .Directives.IsExperimental }}
    {{- $lines := CommentToLines .Description }}
    {{- if $lines }}
"""{{- range $lines }}
{{ . }}{{ end -}}
"""
    {{- end }}
    {{- with .IsDeprecated }}
      {{- $dep := FormatDeprecation $.DeprecationReason }}
      {{- if $dep }}
"""{{- range $dep }}
{{ . }}{{ end -}}
"""
      {{- end }}
    {{- end }}
    {{- if .Directives.IsExperimental }}
"""{{- range (FormatExperimental "") }}
{{ . }}{{ end -}}
"""
    {{- end }}
  {{- end }}
{{- end -}}