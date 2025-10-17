{{ define "method_comment" }}
{{ $desc := CommentToLines .Description }}
{{ $dep := FormatDeprecation .DeprecationReason }}
{{ $exp := FormatExperimental "" }}
{{ if or $desc .IsDeprecated .Directives.IsExperimental }}
        """{{- if $desc -}}
{{- range $i, $line := $desc }}{{ if gt $i 0 }}
        {{ end }}{{ $line }}{{ end -}}
{{- end -}}
{{- if .IsDeprecated -}}
{{- range $i, $line := $dep }}{{ if or (gt $i 0) (or $desc .IsDeprecated) }}
        {{ end }}{{ $line }}{{ end -}}
{{- end -}}
{{- if .Directives.IsExperimental -}}
{{- range $i, $line := $exp }}{{ if or (gt $i 0) (or $desc .IsDeprecated) }}
        {{ end }}{{ $line }}{{ end -}}
{{- end -}}
        """
{{ end }}
{{ end }}
