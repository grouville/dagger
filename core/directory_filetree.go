package core

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/dagger/dagger/dagql"
	bkcontenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/filetree"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/opencontainers/go-digest"
)

type DirectoryFileTree struct {
	Root          filetree.Object `json:"root"`
	ContentDigest digest.Digest   `json:"contentDigest,omitempty"`
	ViewHint      string          `json:"viewHint,omitempty"`
	SourceKey     string          `json:"sourceKey,omitempty"`
}

func NewFileTreeDirectory(platform Platform, root filetree.Object, contentDigest digest.Digest, sourceKey string) *Directory {
	dir := &Directory{
		Platform: platform,
		FileTree: &DirectoryFileTree{Root: root, ContentDigest: contentDigest, SourceKey: sourceKey},
		Lazy:     &DirectoryFileTreeLazy{LazyState: NewLazyState()},
		Dir:      new(LazyAccessor[string, *Directory]),
		Snapshot: new(LazyAccessor[bkcache.ImmutableRef, *Directory]),
	}
	dir.Dir.SetValue("/")
	return dir
}

func (dir *Directory) PersistedContentRefLinks() []dagql.PersistedContentRefLink {
	if dir == nil || dir.FileTree == nil {
		return nil
	}
	return []dagql.PersistedContentRefLink{{Role: "filetree", Digest: dir.FileTree.Root.Digest}}
}

func (dir *Directory) NeedsContentOperationLease() bool {
	return dir != nil && dir.FileTree != nil
}

func (dir *Directory) encodePersistedFileTree(payload persistedDirectoryPayload) (dagql.PersistedObjectEncoding, error) {
	tree := *dir.FileTree
	if err := tree.Root.Validate(); err != nil {
		return dagql.PersistedObjectEncoding{}, err
	}
	if tree.ContentDigest != "" {
		if err := tree.ContentDigest.Validate(); err != nil {
			return dagql.PersistedObjectEncoding{}, err
		}
	}
	if dir.Snapshot != nil {
		if snapshot, ok := dir.Snapshot.Peek(); ok && snapshot != nil {
			tree.ViewHint = snapshot.SnapshotID()
		}
	}
	payload.Form = persistedDirectoryFormFileTree
	payload.FileTree = &tree
	data, err := json.Marshal(payload)
	if err != nil {
		return dagql.PersistedObjectEncoding{}, err
	}
	// Runtime snapshot ownership keeps a live accessor usable. Checkpoint only
	// the CAS root: a restart may collect the old view and reconstruct it without
	// the client or mutable mirror. A snapshot-ID hint is not a persisted edge.
	return dagql.PersistedObjectEncoding{JSON: data, ContentLinks: dir.PersistedContentRefLinks()}, nil
}

type DirectoryFileTreeLazy struct{ LazyState }

func (lazy *DirectoryFileTreeLazy) Evaluate(ctx context.Context, dir *Directory) error {
	return lazy.LazyState.Evaluate(ctx, "directory.filetree", func(ctx context.Context) error {
		if dir.FileTree == nil {
			return errors.New("materialize directory: missing filetree root")
		}
		query, err := CurrentQuery(ctx)
		if err != nil {
			return err
		}
		manager, ok := query.SnapshotManager().(bkcache.FileTreeManager)
		if !ok {
			return errors.New("snapshot manager does not support filetree views")
		}
		ref, err := manager.MaterializeFileTree(ctx, dir.FileTree.Root, dir.FileTree.ViewHint,
			bkcache.WithFileTreeSourceKey(dir.FileTree.SourceKey),
			bkcache.WithDescription(fmt.Sprintf("filetree %s", dir.FileTree.Root.Digest)))
		if err != nil {
			return err
		}
		if dgst := dir.FileTree.ContentDigest; dgst != "" {
			if err := dgst.Validate(); err != nil {
				return errors.Join(err, ref.Release(context.WithoutCancel(ctx)))
			}
			md, ok := ref.(bkcache.RefMetadata)
			if !ok {
				return errors.Join(fmt.Errorf("filetree view metadata: unexpected ref type %T", ref), ref.Release(context.WithoutCancel(ctx)))
			}
			if err := (bkcontenthash.CacheRefMetadata{RefMetadata: md}).SetContentHashKey(dgst); err != nil {
				return errors.Join(err, ref.Release(context.WithoutCancel(ctx)))
			}
		}
		dir.Snapshot.SetValue(ref)
		return nil
	})
}

func (*DirectoryFileTreeLazy) AttachDependencies(context.Context, func(dagql.AnyResult) (dagql.AnyResult, error)) ([]dagql.AnyResult, error) {
	return nil, nil // ownership is a content-root link, not a child DagQL result
}

func (*DirectoryFileTreeLazy) EncodePersisted(context.Context, dagql.PersistedObjectCache) (json.RawMessage, error) {
	return nil, errors.New("filetree directories persist their root, not their materialization callback")
}
