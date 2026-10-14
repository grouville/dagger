package schema

import (
	"context"
	"fmt"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	bkcache "github.com/dagger/dagger/engine/snapshots"
)

type checkpointSourceKey struct{}

type checkpointDirectoryArgs struct {
	Digest   string
	Path     string
	Platform core.Platform
}

func installDirectoryCheckpoint(srv *dagql.Server) {
	dagql.Fields[*core.Query]{
		dagql.NodeFunc("__checkpointDirectory", checkpointDirectory).
			IsPersistable().View(AfterVersion("v1.0.0-0")),
	}.Install(srv)
	dagql.Fields[*core.Directory]{
		dagql.NodeFunc("checkpoint", checkpointSourceDirectory).
			View(AfterVersion("v1.0.0-0")),
	}.Install(srv)
}

func checkpointSourceDirectory(ctx context.Context, source dagql.ObjectResult[*core.Directory], _ struct{}) (dagql.ObjectResult[*core.Directory], error) {
	var result dagql.ObjectResult[*core.Directory]
	cache, err := dagql.EngineCache(ctx)
	if err != nil {
		return result, err
	}
	if err := cache.Evaluate(ctx, source); err != nil {
		return result, err
	}
	if err := checkCheckpointResources(ctx, cache, source); err != nil {
		return result, err
	}
	digest, err := source.Self().DigestPath(ctx, source, ".")
	if err != nil {
		return result, err
	}
	path, err := source.Self().PathOrEval(ctx, source)
	if err != nil {
		return result, err
	}
	srv, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return result, err
	}
	ctx = context.WithValue(ctx, checkpointSourceKey{}, source)
	err = srv.Select(ctx, srv.Root(), &result, dagql.Selector{Field: "__checkpointDirectory", Args: []dagql.NamedInput{
		{Name: "digest", Value: dagql.NewString(digest)},
		{Name: "path", Value: dagql.NewString(path)},
		{Name: "platform", Value: source.Self().Platform},
	}})
	return result, err
}

func checkpointDirectory(ctx context.Context, _ dagql.ObjectResult[*core.Query], args checkpointDirectoryArgs) (dagql.ObjectResult[*core.Directory], error) {
	var result dagql.ObjectResult[*core.Directory]
	source, ok := ctx.Value(checkpointSourceKey{}).(dagql.ObjectResult[*core.Directory])
	if !ok {
		return result, fmt.Errorf("checkpoint is unavailable in the native cache")
	}
	snapshot, ok := source.Self().Snapshot.Peek()
	if !ok || snapshot == nil {
		return result, fmt.Errorf("checkpoint source snapshot is not materialized")
	}
	query, err := core.CurrentQuery(ctx)
	if err != nil {
		return result, err
	}
	pinned, err := query.SnapshotManager().PinSnapshot(ctx, snapshot.SnapshotID())
	if err != nil {
		return result, err
	}
	cache, err := dagql.EngineCache(ctx)
	if err == nil {
		err = checkCheckpointResources(ctx, cache, source)
	}
	if err != nil {
		_ = pinned.Release(context.WithoutCancel(ctx))
		return result, err
	}
	dir := &core.Directory{Platform: args.Platform,
		Dir: new(core.LazyAccessor[string, *core.Directory]), Snapshot: new(core.LazyAccessor[bkcache.ImmutableRef, *core.Directory])}
	dir.SetPath(args.Path)
	dir.SetSnapshot(pinned)
	srv, err := core.CurrentDagqlServer(ctx)
	if err == nil {
		result, err = dagql.NewObjectResultForCurrentCall(ctx, srv, dir)
	}
	if err != nil {
		_ = dir.OnRelease(context.WithoutCancel(ctx))
	}
	return result, err
}

func checkCheckpointResources(ctx context.Context, cache *dagql.Cache, source dagql.ObjectResult[*core.Directory]) error {
	resources, err := cache.ResultHasSessionResources(ctx, source)
	if err != nil {
		return err
	}
	if resources || len(source.Self().Services) != 0 {
		return fmt.Errorf("experimental checkpoint requires a directory without session resources or services")
	}
	return nil
}
