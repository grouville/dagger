package schema

import (
	"context"
	"errors"

	"github.com/dagger/dagger/core"
)

// resolveCallerHostExportPath converts an export path into the caller-host path
// that should receive the export.
//
// Without a workspace, export paths keep their existing caller-host behavior.
// With a local workspace, relative paths resolve from the selected workspace
// cwd, and absolute paths resolve from the workspace root. Remote workspaces
// have no caller-host directory to write to, so hasCallerHostPath is false.
func resolveCallerHostExportPath(ctx context.Context, destPath string) (context.Context, string, bool, error) {
	query, err := core.CurrentQuery(ctx)
	if err != nil {
		return nil, "", false, err
	}
	ws, err := query.CurrentWorkspace(ctx)
	if err != nil {
		if errors.Is(err, core.ErrNoCurrentWorkspace) {
			return ctx, destPath, true, nil
		}
		return nil, "", false, err
	}
	if ws == nil {
		return ctx, destPath, true, nil
	}
	if ws.HostPath() == "" {
		// A remote workspace has no host directory to write to. Match lockfile
		// writes: discard instead of falling back to the caller cwd.
		return nil, "", false, nil
	}

	resolvedPath, err := resolveWorkspacePath(destPath, ws.Cwd)
	if err != nil {
		return nil, "", false, err
	}
	hostPath, err := workspaceHostPath(ws, resolvedPath)
	if err != nil {
		return nil, "", false, err
	}
	ctx, err = withWorkspaceClientContext(ctx, ws)
	if err != nil {
		return nil, "", false, err
	}
	return ctx, hostPath, true, nil
}
