package schema

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/stretchr/testify/require"
)

func TestContainerWithFileDefersSourceFailure(t *testing.T) {
	for _, persisted := range []bool{false, true} {
		name := "new"
		if persisted {
			name = "restored"
		}
		t.Run(name, func(t *testing.T) {
			const sessionID = "withfile-pending-source"
			store := testutil.NewStore(t)
			db := ""
			if persisted {
				db = filepath.Join(t.TempDir(), "cache.db")
			}
			newServer := func() (context.Context, *dagql.Cache, *dagql.Server) {
				ctx, cache, srv := scratchTestCache(t, store, db, sessionID)
				srv.InstallObject(dagql.NewClass[*core.Container](srv))
				srv.InstallObject(dagql.NewClass[*core.File](srv))
				srv.InstallObject(dagql.NewClass[*core.Service](srv))
				dagql.Fields[*core.Query]{
					dagql.Func("readyContainer", func(context.Context, *core.Query, struct{}) (*core.Container, error) {
						ctr := core.NewContainer(core.Platform{OS: "linux", Architecture: "arm64"})
						ctr.Config.WorkingDir = "/work"
						ctr.Config.Entrypoint = []string{"echo"}
						return ctr, nil
					}).IsPersistable(),
					dagql.Func("pendingFile", func(context.Context, *core.Query, struct{}) (*core.File, error) {
						file := &core.File{
							Platform: core.Platform{OS: "linux", Architecture: "arm64"},
							File:     new(core.LazyAccessor[string, *core.File]),
							Snapshot: new(core.LazyAccessor[bkcache.ImmutableRef, *core.File]),
						}
						// The invalid filename fails before any snapshot mount, so this
						// exercises real lazy evaluation without privileged filesystem work.
						file.Lazy = &core.FileBlobLazy{
							LazyState: core.NewLazyState(), Filename: "invalid/name",
						}
						return file, nil
					}).IsPersistable(),
				}.Install(srv)
				dagql.Fields[*core.Container]{
					dagql.NodeFunc("withFile", (&containerSchema{}).withFile).IsPersistable(),
					dagql.NodeFunc("rootfs", (&containerSchema{}).rootfs).IsPersistable(),
					dagql.NodeFunc("asService", (&serviceSchema{}).containerAsService).IsPersistable(),
				}.Install(srv)
				return ctx, cache, srv
			}

			ctx, cache, srv := newServer()
			var parent dagql.ObjectResult[*core.Container]
			var source dagql.ObjectResult[*core.File]
			require.NoError(t, srv.Select(ctx, srv.Root(), &parent, dagql.Selector{Field: "readyContainer"}))
			require.NoError(t, srv.Select(ctx, srv.Root(), &source, dagql.Selector{Field: "pendingFile"}))
			require.False(t, dagql.HasPendingLazyEvaluation(parent), "the destination is already materialized")
			require.True(t, dagql.HasPendingLazyEvaluation(source))
			id, err := source.ID()
			require.NoError(t, err)
			var child dagql.ObjectResult[*core.Container]
			require.NoError(t, srv.Select(ctx, parent, &child, dagql.Selector{
				Field: "withFile",
				Args: []dagql.NamedInput{
					{Name: "path", Value: dagql.String("result")},
					{Name: "source", Value: dagql.NewID[*core.File](id)},
				},
			}))
			require.True(t, dagql.HasPendingLazyEvaluation(source), "construction must not demand the source")

			if persisted {
				record, err := cache.CapturePersistedRecord(ctx, child)
				require.NoError(t, err)
				require.True(t, dagql.HasPendingLazyEvaluation(source), "persistence must not demand the source")
				require.NoError(t, cache.ReleaseSession(ctx, sessionID))
				require.NoError(t, cache.Close(ctx))
				store.Reload(t)
				ctx, cache, srv = newServer()
				restored, err := cache.LoadResultByResultID(ctx, sessionID, srv, record.ResultID)
				require.NoError(t, err)
				child = restored.(dagql.ObjectResult[*core.Container])
			}

			require.NoError(t, cache.EvaluateParts(ctx, child, core.ContainerPartMetadata))
			require.Equal(t, "/work", child.Self().Config.WorkingDir)
			var service dagql.ObjectResult[*core.Service]
			require.NoError(t, srv.Select(ctx, child, &service, dagql.Selector{Field: "asService"}))
			require.Equal(t, []string{"echo"}, service.Self().Args)
			require.True(t, dagql.HasPendingLazyEvaluation(child), "metadata and Service construction leave filesystem work pending")
			require.ErrorContains(t, cache.EvaluateParts(ctx, child, core.ContainerPartFS), "must not contain a directory")
		})
	}
}
