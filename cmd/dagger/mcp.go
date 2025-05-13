package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"dagger.io/dagger/querybuilder"
	"github.com/dagger/dagger/dagql/idtui"
	"github.com/dagger/dagger/engine/client"
	"github.com/spf13/cobra"
)

var (
	mcpStdio      bool
	mcpSseAddr    string
	envPrivileged bool
	envDir        string
)

func init() {
	mcpCmd.PersistentFlags().BoolVar(&mcpStdio, "stdio", true, "Use standard input/output for communicating with the MCP server")
	mcpCmd.PersistentFlags().BoolVar(&envPrivileged, "env-privileged", false, "Expose the core API as tools")
	mcpCmd.PersistentFlags().StringVar(&mcpSseAddr, "sse-addr", "", "Address of the MCP SSE server (no SSE server if empty)")
	mcpCmd.PersistentFlags().StringVar(&envDir, "env-dir", "", "Optional path to a directory that may include input.json (pre-loaded inputs) and/or output.json (captured outputs) for the MCP server")
	_ = mcpCmd.PersistentFlags().MarkHidden("env-dir")
}

var mcpCmd = &cobra.Command{
	Use:   "mcp [options]",
	Short: "Expose a dagger module as an MCP server",
	PreRunE: func(cmd *cobra.Command, args []string) error {
		if progress == "tty" {
			return fmt.Errorf("cannot use tty progress output: it interferes with mcp stdio")
		}

		if progress == "auto" && hasTTY {
			fmt.Fprintln(stderr, "overriding 'auto' progress mode to 'plain' to avoid interference with mcp stdio")

			Frontend = idtui.NewPlain(stderr)
		}

		if cmd.Flags().Changed("env-dir") && strings.TrimSpace(envDir) == "" {
			return errors.New("--env-dir value cannot be empty")
		}

		if envDir != "" {
			info, err := os.Stat(envDir)
			switch {
			case err != nil && os.IsNotExist(err):
				return fmt.Errorf("--env-dir %q does not exist", envDir)
			case err != nil:
				return fmt.Errorf("cannot stat --env-dir: %w", err)
			case !info.IsDir():
				return fmt.Errorf("--env-dir %q is a file, want a directory", envDir)
			}
		}

		return nil
	},
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		cmd.SetContext(idtui.WithPrintTraceLink(ctx, true))
		return withEngine(ctx, client.Params{
			Stdin:  stdin,
			Stdout: stdout,
		}, mcpStart)
	},
	Hidden: true,
	Annotations: map[string]string{
		"experimental": "true",
	},
}

// dagger -m github.com/org/repo mcp
func mcpStart(ctx context.Context, engineClient *client.Client) error {
	if mcpSseAddr != "" || !mcpStdio {
		return errors.New("currently MCP only works with stdio")
	}
	modDef, err := initializeDefaultModule(ctx, engineClient.Dagger())
	if err != nil && err != errModuleNotFound {
		return err
	}

	if err == errModuleNotFound && !envPrivileged {
		return fmt.Errorf("%w and --core not specified", errModuleNotFound)
	}

	q := querybuilder.Query().Client(engineClient.Dagger().GraphQLClient())
	var logMsg string
	var workdirID string

	// TODO: in mcpserver.go this should be overwritten to whatever the MCP client sends us as an MCP Root.
	path := "."
	q = q.Root().Select("host").Select("directory").Arg("path", path).Select("id")
	if err := makeRequest(ctx, q, &workdirID); err != nil {
		return fmt.Errorf("error making workdir: %w", err)
	}

	if modDef != nil {
		// TODO: parse user args and pass them to constructor
		modName := modDef.MainObject.AsObject.Constructor.Name
		q = q.Root().Select(modName).Select("id")

		var modID string
		if err := makeRequest(ctx, q, &modID); err != nil {
			return fmt.Errorf("error instantiating module: %w", err)
		}

		q = q.Root().Select("env").
			Arg("writable", true)

		extraCore := ""
		if envPrivileged {
			q = q.Arg("privileged", envPrivileged)
			extraCore = " and Dagger core"
		}

		q = q.Select("with"+modDef.MainObject.AsObject.Name+"Input").
			Arg("name", modName).
			Arg("value", modID).
			Arg("description", modDef.MainObject.Description())

		logMsg = fmt.Sprintf("Exposing module %q%s as an MCP server on standard input/output", modName, extraCore)
	} else {
		q = q.Root().Select("env").Arg("privileged", envPrivileged)
		logMsg = "Exposing Dagger core as an MCP server"
	}

	q = q.Select("withDirectoryInput").
		Arg("name", "working_dir").
		Arg("value", workdirID).
		Arg("description", "input working directory, often the root of a project")
	// deactivated until a more secure approach is found
	// Select("withDirectoryOutput").
	// Arg("name", "result_dir").
	// Arg("description", "output result directory to be exported to the root of the project")

	// Only preload the environment if envDir/input.json actually exists.
	if envDir != "" {
		inputPath := filepath.Join(envDir, "input.json")

		// Stat the file first; if it isn’t there, just skip pre-loading.
		if info, err := os.Stat(inputPath); err == nil && !info.IsDir() {
			seed, err := loadEnvFromFile(inputPath)
			if err != nil {
				return fmt.Errorf("invalid env-file %q: %w", inputPath, err)
			}

			for _, in := range seed.Inputs {
				q = q.Select("withStringInput").
					Arg("name", in.Key).
					Arg("value", in.Value).
					Arg("description", in.Description)
			}
			for _, out := range seed.Outputs {
				q = q.Select("withStringOutput").
					Arg("name", out.Key).
					Arg("description", out.Description)
			}
		} else if err != nil && !errors.Is(err, os.ErrNotExist) {
			// A real error (e.g., permission issue) occurred while stat’ing the file.
			return fmt.Errorf("cannot stat %q: %w", inputPath, err)
		}
	}

	q = q.Select("id")

	var envID string
	if err := makeRequest(ctx, q, &envID); err != nil {
		return fmt.Errorf("error making environment: %w", err)
	}

	fmt.Fprintln(stderr, logMsg)
	call := q.Root().
		Select("llm").
		Select("withEnv").
		Arg("env", envID).
		Select("__mcp")

	// this passes the arg to the mcp server
	// which uses it to export the state to envdir/output.json
	if envDir != "" {
		call = call.Arg("envDir", envDir)
	}

	var response any
	if err := makeRequest(ctx, call, &response); err != nil {
		return fmt.Errorf("error starting MCP server: %w", err)
	}

	return nil
}

// todo(after): move this to core ? How to do it cleanly?
type Binding struct {
	Key   string
	Value string // will be any

	Description string
	// The expected type
	// Used when defining an output
	// ExpectedType string
}

type BindingMap map[string]Binding
type Env struct {
	Inputs  BindingMap `json:"inputs"`
	Outputs BindingMap `json:"outputs"`
}

func loadEnvFromFile(p string) (*Env, error) {
	data, err := os.ReadFile(p)
	if err != nil {
		return nil, err
	}
	var e *Env
	if err := json.Unmarshal(data, &e); err != nil {
		return nil, err
	}
	return e, nil
}
