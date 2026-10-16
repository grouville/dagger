package templates

import (
	"go/format"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

// Compile and run the generated dispatcher against the real SDK transport.
func TestDispatchInputs(t *testing.T) {
	dir := t.TempDir()
	source := `package main
import (
 "context"
 "encoding/json"
 "fmt"
 "log/slog"
 "os"
 "sort"
 dagger "dagger.io/dagger/core"
 "github.com/dagger/querybuilder"
 telemetry "github.com/dagger/otel-go"
 "github.com/vektah/gqlparser/v2/gqlerror"
 "go.opentelemetry.io/otel/sdk/resource"
 semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)
type DaggerObject interface {
 querybuilder.GraphQLMarshaller
 ID(context.Context) (dagger.ID, error)
}
` + mainSrc(func(string) bool { return true })
	formatted, err := format.Source([]byte(source))
	require.NoError(t, err)
	mainPath := filepath.Join(dir, "main.go")
	require.NoError(t, os.WriteFile(mainPath, formatted, 0600))
	testSource, err := os.ReadFile("testdata/dispatch/main_test.go")
	require.NoError(t, err)
	testPath := filepath.Join(dir, "main_test.go")
	require.NoError(t, os.WriteFile(testPath, testSource, 0600))
	cmd := exec.CommandContext(t.Context(), "go", "test", "-count=1", mainPath, testPath)
	output, err := cmd.CombinedOutput()
	require.NoError(t, err, "%s", output)
}
