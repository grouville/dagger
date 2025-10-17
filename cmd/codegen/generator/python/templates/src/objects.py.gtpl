{{ define "objects" }}
{{ range $index, $type := .Types }}{{ if and (eq $type.Kind "OBJECT") (not (HasPrefix $type.Name "_")) }}{{ if gt $index 0 }}

{{ end }}{{ template "object" $type }}{{ end }}{{ end }}
{{ end }}

{{ define "object" }}
{{ $cls := .Name | QueryToClient }}
@typecheck
class {{ $cls }}({{ if eq .Name "Query" }}Root{{ else }}Type{{ end }}):
{{ if .Description }}    """{{- $lines := CommentToLines .Description -}}{{- range $i, $line := $lines }}{{ if gt $i 0 }}
    {{ end }}{{ $line }}{{ end }}"""
{{ end }}{{ $fields := .Fields }}{{ if not $fields }}
    ...
{{ else }}{{ range $field := $fields }}
{{ if and (ne $field.TypeRef.Kind "") (ne $field.Name "") }}{{ if IsLeaf $field.TypeRef }}{{ template "method_solve" $field }}{{ else }}{{ template "method" $field }}{{ end }}{{ end }}
{{ end }}{{ end }}
{{ if . | IsSelfChainable }}
    def with_(self, cb: Callable[["{{ $cls }}"], "{{ $cls }}"]) -> "{{ $cls }}":
        """Call the provided callable with current {{ $cls }}.

        This is useful for reusability and readability by not breaking the calling chain.
        """
        return cb(self)
{{ end }}
{{ end }}
