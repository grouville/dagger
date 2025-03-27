package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"dagger.io/dagger"
	"github.com/dagger/dagger/internal/testutil"
	"github.com/dagger/testctx"
	"github.com/dagger/testctx/oteltest"
	"github.com/stretchr/testify/require"
)

func TestMain(m *testing.M) {
	os.Exit(oteltest.Main(m))
}

func Middleware() []testctx.Middleware[*testing.T] {
	return []testctx.Middleware[*testing.T]{
		oteltest.WithTracing[*testing.T](
			oteltest.TraceConfig[*testing.T]{
				StartOptions: testutil.SpanOpts[*testing.T],
			},
		),
		oteltest.WithLogging[*testing.T](),
	}
}

type DaggerCMDSuite struct{}

func TestDaggerCMD(tt *testing.T) {
	testctx.New(tt, Middleware()...).RunTests(DaggerCMDSuite{})
}

// getLocalDaggerCliPath finds the path to the dagger CLI binary.
func getLocalDaggerCliPath(t testing.TB) string {
	t.Helper()
	cliPath := os.Getenv("_EXPERIMENTAL_DAGGER_CLI_BIN")
	if cliPath == "" {
		var err error
		cliPath, err = exec.LookPath("dagger")
		require.NoError(t, err, "dagger binary not found in PATH")
	}
	require.NotEmpty(t, cliPath, "dagger binary path is empty even after LookPath")
	return cliPath
}

// runHostDaggerCommand executes the dagger CLI on the host.
func runHostDaggerCommand(ctx context.Context, t testing.TB, workdir string, args ...string) error {
	t.Helper()
	cmd := exec.CommandContext(ctx, getLocalDaggerCliPath(t), args...)
	cmd.Env = os.Environ()
	cmd.Dir = workdir

	outputBytes, err := cmd.CombinedOutput()
	output := string(outputBytes)
	logMsg := fmt.Sprintf("Host command:\nDir: %s\nArgs: %v\nOutput:\n%s", workdir, cmd.Args, output)

	if err != nil {
		t.Logf("FAILED %s", logMsg)
		return fmt.Errorf("host command failed: %w", err)
	}
	t.Logf("SUCCESS %s", logMsg)
	return nil
}

// assertAutocomplete performs the actual autocompletion call and assertion.
func assertAutocomplete(t *testctx.T, autoComplete shellAutoComplete, cmdlineToTest string) {
	t.Helper()

	start := strings.IndexRune(cmdlineToTest, '<')
	end := strings.IndexRune(cmdlineToTest, '>')
	require.True(t, start != -1 && end != -1 && start < end, "invalid cmdline format: %q", cmdlineToTest)

	expr := cmdlineToTest[start+1 : end]
	inprogress, rest, ok := strings.Cut(expr, "$")
	require.True(t, ok, "invalid cmdline format (missing '$'): %q", cmdlineToTest)

	expected := strings.TrimSpace(inprogress + rest)

	lineContent := cmdlineToTest[:start] + inprogress + cmdlineToTest[end+1:]
	cursor := start + len(inprogress)

	t.Logf("Testing line: %q, cursor: %d, expecting: %q", lineContent, cursor, expected)

	_, comp := autoComplete.Do([][]rune{[]rune(lineContent)}, 0, cursor)
	require.NotNil(t, comp, "completion object should not be nil")
	require.Equal(t, 1, comp.NumCategories(), "expected exactly one completion category")

	var candidates []string
	// Only try to get entries if we actually have the expected category count (1)
	if comp.NumCategories() == 1 {
		candidates = make([]string, 0, comp.NumEntries(0))
		for i := 0; i < comp.NumEntries(0); i++ {
			entry := comp.Entry(0, i)
			t.Logf("entry %d: %s (%q)", i, entry.Title(), entry.Description())
			candidates = append(candidates, entry.Title())
		}
	} else {
		// todo(guillaume): reintroduce logic
	}

	require.Contains(t, candidates, expected, "expected candidate %q not found in %v", expected, candidates)
}

type shellAutocompleteTestCase struct {
	Name           string
	CmdlinesToTest []string
	setup          func(ctx context.Context, t *testctx.T, tmpDir string) (moduleRootRelPath string, err error)
	Env            [][2]string
}

func (DaggerCMDSuite) TestShellAutocomplete(ctx context.Context, t *testctx.T) {
	testCases := []shellAutocompleteTestCase{
		{
			Name: "WithStandardWolfiModule",
			CmdlinesToTest: []string{
				// top-level function
				`<con$tainer >`,
				`<$container >`,
				`  <$container >`,
				`<con$tainer > "alpine:latest"`,
				`<con$tainer >| directory`,

				// top-level deps (assuming 'alpine' is a valid dep in this context)
				`<a$lpine >`,

				// stdlib fallback
				`<dir$ectory >`,
				`directory | <with$-new-file >`,

				// chaining
				`container | <$directory >`,
				`container | <$with-directory >`,
				`container | <dir$ectory >`,
				`container | <with-$directory >`,
				`container | directory "./path" | <f$ile >`,

				// subshells
				`container | with-directory $(<$container >)`,
				`container | with-directory $(<con$tainer >)`,
				`container | with-directory $(container | <$directory >)`,
				`container | with-directory $(container | <dir$ectory >)`,

				// args
				`container <--$platform >`, // Using platform as a common arg example
				`container <--$platform > | directory`,
				`container | directory <--$path >`, // Using path as a common arg example

				// TODO: These have been hidden. Uncomment when stable, or put them
				// behind a feature flag so they can be tested even if hidden.

				// // .deps builtin
				// `.deps | <$alpine >`,
				// `.deps | <a$lpine >`,
				//
				// // .stdlib builtin
				// `.stdlib | <$container >`,
				// `.stdlib | <con$tainer >`,
				// `.stdlib | container <--$platform >`,
				// `.stdlib | container | <dir$ectory >`,
				//
				// // .core builtin
				// `.core | <con$tainer >`,
				// `.core | container <--$platform >`,
				// `.core | container | <dir$ectory >`,

				// FIXME: avoid inserting extra spaces
				// `<contain$er> `,
			},
			Env: [][2]string{{"DAGGER_MODULE", "./wolfi"}}, // Explicitly set module context
			setup: func(ctx context.Context, t *testctx.T, tmpDir string) (string, error) {
				wd, err := os.Getwd()
				if err != nil {
					return "", err
				}
				moduleSrcDir := filepath.Join(wd, "../../modules")
				cpCmd := exec.CommandContext(ctx, "cp", "-r", filepath.Join(moduleSrcDir, "."), tmpDir)
				output, err := cpCmd.CombinedOutput()
				if err != nil {
					return "", fmt.Errorf("failed to copy modules from %s: %w\nOutput:\n%s", moduleSrcDir, err, output)
				}
				t.Logf("Copied modules from %s", moduleSrcDir)
				gitCmd := exec.CommandContext(ctx, "git", "init")
				gitCmd.Dir = tmpDir
				output, err = gitCmd.CombinedOutput()
				if err != nil {
					t.Logf("git init failed (non-fatal): %s", output)
				}
				return ".", nil
			},
		},
		{
			Name: "WithNoSDKModule",
			CmdlinesToTest: []string{
				// Complete the 'hello' module name installed in 'test'
				`<hel$lo >`,
				`<$hello >`,

				// // Complete the 'hello' function within the 'hello' module
				// // Note: These might still fail if the underlying completion logic issue persists,
				// // but they represent the correct scenario for this simplified setup.
				// `hello | <$hello>`,
				// `hello | <hel$lo >`,

				`<con$tainer >`,
				`<dir$ectory >`,
			},
			setup: func(ctx context.Context, t *testctx.T, tmpDir string) (string, error) {
				testModDir := filepath.Join(tmpDir, "test")
				helloModDir := filepath.Join(testModDir, "hello")

				helloCode := `package main
 type Hello struct{}
 func (m *Hello) Hello() string { return "hi" }`

				// Create 'hello' directory
				if err := os.MkdirAll(helloModDir, 0755); err != nil {
					return "", fmt.Errorf("failed to create hello module dir: %w", err)
				}
				// Write 'hello' source
				if err := os.WriteFile(filepath.Join(helloModDir, "main.go"), []byte(helloCode), 0644); err != nil {
					return "", fmt.Errorf("failed to write hello module source: %w", err)
				}
				t.Logf("Created hello module file at %s", helloModDir)

				// Init 'hello' module (with SDK)
				if err := runHostDaggerCommand(ctx, t, helloModDir, "init", "--sdk=go", "--name=hello"); err != nil {
					return "", fmt.Errorf("failed to init hello module: %w", err)
				}

				// Create 'test' directory (MkdirAll handles if it exists)
				if err := os.MkdirAll(testModDir, 0755); err != nil {
					return "", fmt.Errorf("failed to create test module dir: %w", err)
				}

				// Init 'test' module (no SDK)
				if err := runHostDaggerCommand(ctx, t, testModDir, "init", "--name=test"); err != nil {
					return "", fmt.Errorf("failed to init test module: %w", err)
				}

				// Install 'hello' directly into 'test'
				if err := runHostDaggerCommand(ctx, t, testModDir, "install", "./hello"); err != nil {
					return "", fmt.Errorf("failed to install hello module into test module: %w", err)
				}

				// The module context to run tests in is 'test'
				return "test", nil
			},
		},
	}

	originalWD, err := os.Getwd()
	require.NoError(t, err)
	for _, tc := range testCases {
		tc := tc
		t.Run(tc.Name, func(ctx context.Context, t *testctx.T) {
			tmpDir := t.TempDir()
			t.Cleanup(func() {
				if err := os.Chdir(originalWD); err != nil {
					t.Logf("WARN: Failed to chdir back to original directory %q: %v", originalWD, err)
				}
			})
			moduleRootRelPath, err := tc.setup(ctx, t, tmpDir)
			require.NoError(t, err, "Setup failed for scenario %s", tc.Name)
			moduleDirAbs := filepath.Join(tmpDir, moduleRootRelPath)
			require.DirExists(t, moduleDirAbs)
			require.NoError(t, os.Chdir(moduleDirAbs), "Failed to chdir to module root %s", moduleDirAbs)
			t.Logf("Changed CWD to module root: %s", moduleDirAbs)
			for _, envVar := range tc.Env {
				t.Setenv(envVar[0], envVar[1])
				t.Logf("Setenv: %s=%s", envVar[0], envVar[1])
			}
			client, err := dagger.Connect(ctx)
			require.NoError(t, err, "Dagger connect failed")
			t.Cleanup(func() { client.Close() })
			var debug bool
			handler := &shellCallHandler{dag: client, debug: debug}
			require.NoError(t, handler.RunAll(ctx, nil), "Handler RunAll failed")
			autoComplete := shellAutoComplete{handler}
			for _, cmdline := range tc.CmdlinesToTest {
				cmdlineToAssert := cmdline
				t.Run(cmdlineToAssert, func(ctx context.Context, t *testctx.T) {
					assertAutocomplete(t, autoComplete, cmdlineToAssert)
				})
			}
		})
	}
}
