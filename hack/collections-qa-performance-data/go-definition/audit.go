// Diagnostic only: inventory the generated registration expression. This does
// not validate Go programs, install schemas, or bypass Dagger's runtime.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"
)

func definition(data []byte) (ast.Expr, *token.FileSet, error) {
	fs := token.NewFileSet()
	file, err := parser.ParseFile(fs, "dagger.gen.go", data, parser.SkipObjectResolution)
	if err != nil {
		return nil, nil, err
	}
	for _, d := range file.Decls {
		fn, ok := d.(*ast.FuncDecl)
		if !ok || fn.Name.Name != "invoke" || fn.Body == nil {
			continue
		}
		for _, stmt := range fn.Body.List {
			sw, ok := stmt.(*ast.SwitchStmt)
			if !ok {
				continue
			}
			tag, ok := sw.Tag.(*ast.Ident)
			if !ok || tag.Name != "parentName" {
				continue
			}
			for _, clause := range sw.Body.List {
				c := clause.(*ast.CaseClause)
				if len(c.List) != 1 || len(c.Body) != 1 {
					continue
				}
				lit, ok := c.List[0].(*ast.BasicLit)
				if !ok || lit.Kind != token.STRING {
					continue
				}
				value, err := strconv.Unquote(lit.Value)
				if err != nil || value != "" {
					continue
				}
				ret, ok := c.Body[0].(*ast.ReturnStmt)
				if !ok || len(ret.Results) != 2 {
					continue
				}
				return ret.Results[0], fs, nil
			}
		}
	}
	return nil, nil, fmt.Errorf("no simple generated definition")
}

func main() {
	for _, path := range os.Args[1:] {
		data, err := os.ReadFile(path)
		if err != nil {
			panic(err)
		}
		expr, fs, err := definition(data)
		if err != nil {
			panic(err)
		}
		var buf bytes.Buffer
		if err := format.Node(&buf, fs, expr); err != nil {
			panic(err)
		}
		calls := map[string]int{}
		functions := []string{}
		ast.Inspect(expr, func(n ast.Node) bool {
			call, ok := n.(*ast.CallExpr)
			if !ok {
				return true
			}
			sel, ok := call.Fun.(*ast.SelectorExpr)
			if !ok {
				return true
			}
			calls[sel.Sel.Name]++
			if sel.Sel.Name == "Function" && len(call.Args) > 0 {
				if lit, ok := call.Args[0].(*ast.BasicLit); ok {
					name, _ := strconv.Unquote(lit.Value)
					functions = append(functions, name)
				}
			}
			return true
		})
		sort.Strings(functions)
		durations := make([]time.Duration, 1000)
		for i := range durations {
			start := time.Now()
			if _, _, err := definition(data); err != nil {
				panic(err)
			}
			durations[i] = time.Since(start)
		}
		sort.Slice(durations, func(i, j int) bool { return durations[i] < durations[j] })
		row := map[string]any{"module": filepath.Base(filepath.Dir(path)), "generated_file_bytes": len(data), "registration_expression_bytes": buf.Len(), "functions": functions, "registration_calls": calls, "parse_only_median_microseconds": float64(durations[len(durations)/2]) / float64(time.Microsecond), "parse_only_p95_microseconds": float64(durations[len(durations)*95/100]) / float64(time.Microsecond), "iterations": len(durations), "scope": "in-memory parse of existing generated file, excludes file I/O, source validation, schema installation and any Dagger command"}
		raw, _ := json.Marshal(row)
		fmt.Println(string(raw))
	}
}
