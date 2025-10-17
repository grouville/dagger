{{- define "method_solve" -}}
  {{- $required := RequiredArgs . -}}
  {{- $optional := OptionalArgs . -}}
  {{- $convertID := ConvertID . -}}

  async def {{ .Name | FormatPyName }}(self{{ if or $required $optional }}, {{ template "args" . }}{{ end }}) -> {{ if IsVoid . }}None{{ else }}{{ .TypeRef | FormatOutputType }}{{ end }}:
{{- template "method_docstring" . }}
{{- template "call_args" . }}
    {{- if $convertID }}
    return await self._ctx.execute_sync(self, "{{ .Name }}", _args)
    {{- else }}
    _ctx = self._select("{{ .Name }}", _args)
      {{- if IsVoid . }}
    await _ctx.execute()
      {{- else if and .TypeRef.IsList (IsListOfObject .TypeRef) }}
    return await _ctx.execute_object_list({{ . | FormatReturnType | ToSingleType }})
      {{- else if and .TypeRef.IsList (IsListOfEnum .TypeRef) }}
    return await _ctx.execute({{ . | FormatReturnType }})
      {{- else }}
    return await _ctx.execute({{ .TypeRef | FormatOutputType }})
      {{- end }}
    {{- end }}

  {{- if and $convertID (eq .Name "sync") }}
  def __await__(self):
      return self.sync().__await__()
  {{- end }}
{{- end -}}
