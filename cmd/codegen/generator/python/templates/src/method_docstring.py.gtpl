{{ define "method_docstring" }}
{{ $lines := MethodDocLines . }}
{{ if $lines }}
{{- if eq (len $lines) 1 }}        """{{ index $lines 0 }}"""

{{- else }}        """{{ index $lines 0 }}
{{- range $i, $line := $lines }}{{- if eq $i 0 }}{{ continue }}{{ end }}
{{- if eq $line "" }}
        
{{- else }}
        {{ $line }}
{{- end }}
{{- end }}
        """
{{- end }}
{{ end }}
{{ end }}
