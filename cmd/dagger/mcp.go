package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
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
	envFile       string
	exportEnv     bool
)

func init() {
	mcpCmd.PersistentFlags().BoolVar(&mcpStdio, "stdio", true, "Use standard input/output for communicating with the MCP server")
	mcpCmd.PersistentFlags().BoolVar(&envPrivileged, "env-privileged", false, "Expose the core API as tools")
	mcpCmd.PersistentFlags().StringVar(&mcpSseAddr, "sse-addr", "", "Address of the MCP SSE server (no SSE server if empty)")
	mcpCmd.PersistentFlags().StringVar(&envFile, "env-file", "", "Path to a JSON file used to load the initial MCP environment before starting the server (experimental)")
	_ = mcpCmd.PersistentFlags().MarkHidden("env-file") // mark it as hidden to avoid showing it in the help
	mcpCmd.PersistentFlags().
		BoolVar(&exportEnv, "export-env", false,
			"Write final environment JSON to /tmp/declare/output (experimental)")
	_ = mcpCmd.PersistentFlags().MarkHidden("export-env")
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

		if cmd.Flags().Changed("env-file") && strings.TrimSpace(envFile) == "" {
			return errors.New("--env-file value cannot be empty")
		}

		if envFile != "" {
			info, err := os.Stat(envFile)
			switch {
			case err != nil && os.IsNotExist(err):
				return fmt.Errorf("--env-file %q does not exist", envFile)
			case err != nil:
				return fmt.Errorf("cannot stat --env-file: %w", err)
			case info.IsDir():
				return fmt.Errorf("--env-file %q is a directory, want a JSON file", envFile)
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
			Arg("description", modDef.MainObject.Description()).
			// this should disappear with the hot reload work from Connor
			Select("withDirectoryInput").
			Arg("name", "working_dir").
			Arg("value", workdirID).
			Arg("description", "input working directory, often the root of a project").
			Select("withDirectoryOutput").
			Arg("name", "result_dir").
			Arg("description", "output result directory to be exported to the root of the project")

		// TODO: import the env move the string scalar
		if envFile != "" {
			seed, err := loadEnvFromFile(envFile)
			if err != nil {
				return fmt.Errorf("invalid env-file: %w", err)
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
					Arg("value", out.Value).
					Arg("description", out.Description)
			}
		}

		q = q.Select("id")

		logMsg = fmt.Sprintf("Exposing module %q%s as an MCP server on standard input/output", modName, extraCore)
	} else {
		q = q.Root().Select("env").Arg("privileged", envPrivileged)
		logMsg = "Exposing Dagger core as an MCP server"
	}

	q = q.Select("withDirectoryInput").
		Arg("name", "working_dir").
		Arg("value", workdirID).
		Arg("description", "input working directory, often the root of a project").
		Select("withDirectoryOutput").
		Arg("name", "result_dir").
		Arg("description", "output result directory to be exported to the root of the project").
		Select("id")

	var envID string
	if err := makeRequest(ctx, q, &envID); err != nil {
		return fmt.Errorf("error making environment: %w", err)
	}

	fmt.Fprintln(stderr, logMsg)
	q = q.Root().
		Select("llm").
		Select("withEnv").
		Arg("env", envID).
		Select("__mcp").
		Arg("exportEnv", exportEnv)

	var response any
	if err := makeRequest(ctx, q, &response); err != nil {
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

type Env struct {
	Inputs  []Binding
	Outputs []Binding
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
