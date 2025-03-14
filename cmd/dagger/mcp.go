package main

import (
	"context"
	"fmt"

	"dagger.io/dagger/querybuilder"
	"github.com/dagger/dagger/dagql/idtui"
	"github.com/dagger/dagger/engine/client"
	"github.com/spf13/cobra"
)

var (
	mcpStdio   bool
	mcpSseAddr string
)

func init() {
	mcpCmd.PersistentFlags().BoolVar(&mcpStdio, "stdio", true, "Use standard input/output for communicating with the MCP server")
	mcpCmd.PersistentFlags().StringVar(&mcpSseAddr, "sse-addr", "", "Address of the MCP SSE server (no SSE server if empty)")
}

// dagger mcp serve
// dagger mcp list

var mcpCmd = &cobra.Command{
	Use:   "mcp [options]",
	Short: "Expose a dagger module as an MCP server",
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SetContext(idtui.WithPrintTraceLink(cmd.Context(), true))
		return withEngine(cmd.Context(), client.Params{}, mcpStart)
	},
	Hidden: true,
	Annotations: map[string]string{
		"experimental": "true",
	},
}

// dagger -m github.com/org/repo mcp serve key1=val1 key2=val2
func mcpStart(ctx context.Context, engineClient *client.Client) error {
	modDef, err := initializeDefaultModule(ctx, engineClient.Dagger())
	if err != nil {
		return err
	}
	q := querybuilder.Query().Client(engineClient.Dagger().GraphQLClient())
	// TODO: pass in args
	q = q.Root().Select(modDef.MainObject.AsObject.Constructor.Name).Select("id")

	var modId string
	if err := makeRequest(ctx, q, &modId); err != nil {
		return fmt.Errorf("error making request: %w", err)
	}

	q = q.Root().
		Select("llm").
		Select("with"+modDef.MainObject.AsObject.Name).
		Arg("value", modId).
		Select("mcp")

	var response any
	if err := makeRequest(ctx, q, &response); err != nil {
		return fmt.Errorf("error making request: %w", err)
	}

	return nil
}
