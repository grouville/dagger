package templates

import (
	"embed"
	"fmt"
	"text/template"

	"github.com/dagger/dagger/cmd/codegen/generator"
)

//go:embed src
var srcs embed.FS

func New(schemaVersion string, cfg generator.Config) *template.Template {
	top := "api"
	deps := []string{
		top,
		"header", "types",
		"objects",
		"method", "method_solve", "args", "call_args", "method_docstring",
		"default",
	}

	fns := PythonTemplateFuncs(schemaVersion, cfg)
	files := make([]string, 0, len(deps))
	for _, t := range deps {
		files = append(files, fmt.Sprintf("src/%s.py.gtpl", t))
	}
	return template.Must(template.New(top).Funcs(fns).ParseFS(srcs, files...))
}
