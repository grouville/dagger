package templates

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
)

func TestGeneratedDispatchReadsCallOnce(t *testing.T) {
	// Compile the emitted entrypoint against the actual SDK. The server only
	// supplies call metadata and records what the entrypoint sends back.
	dir := t.TempDir()
	sdkDir, err := filepath.Abs("../../../../../sdk/go")
	require.NoError(t, err)
	mod, err := os.ReadFile(filepath.Join(sdkDir, "go.mod"))
	require.NoError(t, err)
	modText := strings.Replace(string(mod), "module dagger.io/dagger", "module dispatchtest", 1)
	modText += fmt.Sprintf("\nrequire dagger.io/dagger v0.0.0\nreplace dagger.io/dagger => %q\n", sdkDir)
	require.NoError(t, os.WriteFile(filepath.Join(dir, "go.mod"), []byte(modText), 0600))
	sum, err := os.ReadFile(filepath.Join(sdkDir, "go.sum"))
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(filepath.Join(dir, "go.sum"), sum, 0600))
	source := dispatchTestProgram + mainSrc(func(string) bool { return true })
	require.NoError(t, os.WriteFile(filepath.Join(dir, "main.go"), []byte(source), 0600))
	binary := filepath.Join(dir, "dispatch")
	build := exec.CommandContext(t.Context(), "go", "build", "-mod=mod", "-buildvcs=false", "-o", binary, ".")
	build.Dir = dir
	out, err := build.CombinedOutput()
	require.NoError(t, err, string(out))

	for _, tc := range []struct {
		name          string
		parentName    string
		function      string
		args          map[string]string
		metadataError bool
	}{
		{name: "module initialization"},
		{name: "method without arguments", parentName: "Example", function: "empty"},
		{name: "JSON arguments", parentName: "Example", function: "echo", args: map[string]string{
			"text": `"quoted \"text\" and λ"`, "null": "null", "boolean": "false",
			"nested": `{"items":[1,"two",null]}`, "directory": `"Directory@opaque-id"`,
		}},
		{name: "function error", parentName: "Example", function: "fail"},
		{name: "metadata error", metadataError: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			parent := `{"Counter":3,"Text":"λ"}`
			var args []map[string]string
			byID := map[string]map[string]string{}
			for name, value := range tc.args {
				require.True(t, json.Valid([]byte(value)), name)
				arg := map[string]string{"id": name + "-id", "name": name, "value": value}
				args = append(args, arg)
				byID[arg["id"]] = arg
			}
			metadata := map[string]any{"parentName": tc.parentName, "name": tc.function, "parent": parent, "inputArgs": args}
			var mu sync.Mutex
			requests := 0
			returnedError := false
			var returnedMessage string
			var returned struct {
				ParentName string
				Name       string
				Parent     string
				Args       map[string]string
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var request struct{ Query string }
				if !assert.NoError(t, json.NewDecoder(r.Body).Decode(&request)) {
					return
				}
				doc, err := parser.ParseQuery(&ast.Source{Input: request.Query})
				if !assert.NoError(t, err) {
					return
				}
				mu.Lock()
				defer mu.Unlock()
				data := map[string]any{}
				for _, selection := range doc.Operations[0].SelectionSet {
					field := selection.(*ast.Field)
					key := field.Alias
					if key == "" {
						key = field.Name
					}
					switch field.Name {
					case "error":
						message, err := field.Arguments.ForName("message").Value.Value(nil)
						if !assert.NoError(t, err) {
							return
						}
						returnedMessage = message.(string)
						data[key] = map[string]any{"id": "error-id"}
					case "node":
						requests++
						id, err := field.Arguments.ForName("id").Value.Value(nil)
						if !assert.NoError(t, err) {
							return
						}
						data[key] = byID[id.(string)]
					case "currentFunctionCall":
						result := map[string]any{}
						returning := false
						for _, child := range field.SelectionSet {
							child := child.(*ast.Field)
							if child.Name == "returnValue" {
								returning = true
								value, err := child.Arguments.ForName("value").Value.Value(nil)
								if !assert.NoError(t, err) || !assert.NoError(t, json.Unmarshal([]byte(value.(string)), &returned)) {
									return
								}
								result[child.Name] = nil
							} else if child.Name == "returnError" {
								returning = true
								returnedError = true
								result[child.Name] = nil
							}
						}
						if !returning {
							requests++
							if tc.metadataError {
								assert.NoError(t, json.NewEncoder(w).Encode(map[string]any{"errors": []map[string]string{{"message": "metadata unavailable"}}}))
								return
							}
							result = metadata
						}
						data[key] = result
					default:
						t.Errorf("unexpected query: %s", request.Query)
					}
				}
				assert.NoError(t, json.NewEncoder(w).Encode(map[string]any{"data": data}))
			}))
			defer server.Close()
			command := exec.CommandContext(t.Context(), binary)
			for _, env := range os.Environ() {
				if !strings.HasPrefix(env, "DAGGER_") && !strings.HasPrefix(env, "OTEL_") {
					command.Env = append(command.Env, env)
				}
			}
			port := strings.TrimPrefix(server.URL, "http://127.0.0.1:")
			command.Env = append(command.Env, "DAGGER_SESSION_PORT="+port, "DAGGER_SESSION_TOKEN=test",
				"OTEL_SDK_DISABLED=true", "OTEL_TRACES_EXPORTER=none", "OTEL_LOGS_EXPORTER=none", "OTEL_METRICS_EXPORTER=none")
			out, err := command.CombinedOutput()
			mu.Lock()
			defer mu.Unlock()
			if tc.function == "fail" || tc.metadataError {
				require.Error(t, err, string(out))
				require.True(t, returnedError, string(out))
				if tc.metadataError {
					require.Contains(t, returnedMessage, "metadata unavailable")
				} else {
					require.Equal(t, "user failure", returnedMessage)
				}
			} else {
				require.NoError(t, err, string(out))
				require.Equal(t, tc.parentName, returned.ParentName)
				require.Equal(t, tc.function, returned.Name)
				require.Equal(t, parent, returned.Parent)
				require.Len(t, returned.Args, len(tc.args))
				for name, value := range tc.args {
					require.Equal(t, value, returned.Args[name], name)
				}
			}
			require.Equal(t, 1, requests, "call metadata must be read in one request")
		})
	}
}

const dispatchTestProgram = `package main
import (
 "context"
 "encoding/json"
 "errors"
 "fmt"
 "log/slog"
 "os"
 "sort"
 client "dagger.io/dagger"
 dagger "dagger.io/dagger/core"
 telemetry "github.com/dagger/otel-go"
 "github.com/vektah/gqlparser/v2/gqlerror"
 "go.opentelemetry.io/otel/sdk/resource"
 semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)
var dag *dagger.Query
func init() {
 c, err := client.Connect(context.Background())
 if err != nil { panic(err) }
 dag = dagger.NewQuery(c)
}
func setMarshalContext(context.Context) {}
func invoke(_ context.Context, parent []byte, parentName, name string, args map[string][]byte) (any, error) {
 if name == "fail" { return nil, errors.New("user failure") }
 values := make(map[string]string, len(args))
 for key, value := range args { values[key] = string(value) }
 return struct {
  ParentName string
  Name string
  Parent string
  Args map[string]string
 }{parentName, name, string(parent), values}, nil
}
`
