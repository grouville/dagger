{{ define "method" }}
{{ $required := RequiredArgs . }}
{{ $optional := OptionalArgs . }}
{{ $convertID := ConvertID . }}
    def {{ .Name | FormatPyName }}(self{{ if or $required $optional }}, {{ template "args" . }}{{ end }}) -> {{ if ReturnSelf . }}Self{{ else }}{{ .TypeRef | FormatOutputType }}{{ end }}:
{{ template "method_docstring" . }}
{{ template "call_args" . }}
{{ if $convertID }}        return await self._ctx.execute_sync(self, "{{ .Name }}", _args)
{{ else }}        _ctx = self._select("{{ .Name }}", _args)
        return {{ if ReturnSelf . }}self.__class__{{ else }}{{ .TypeRef | FormatOutputType }}{{ end }}(_ctx)
{{ end }}
{{ if and $convertID (eq .Name "sync") }}
    def __await__(self):
        return self.sync().__await__()
{{ end }}
{{ end }}
