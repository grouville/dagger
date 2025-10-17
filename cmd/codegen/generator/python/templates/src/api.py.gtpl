{{ define "api" -}}
{{- template "header" . -}}
{{ "" }}
{{- template "types" . -}}
{{ "" }}
{{- template "objects" . -}}
{{ "" }}
{{- template "default" . -}}
{{- end -}}