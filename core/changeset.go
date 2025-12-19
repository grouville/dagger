package core

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"

	"dagger.io/dagger/telemetry"
	"github.com/containerd/containerd/v2/core/mount"
	containerdfs "github.com/containerd/continuity/fs"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine/buildkit"
	bkcache "github.com/dagger/dagger/internal/buildkit/cache"
	bkclient "github.com/dagger/dagger/internal/buildkit/client"
	"github.com/dagger/dagger/internal/buildkit/solver/pb"
	"github.com/vektah/gqlparser/v2/ast"
	"go.opentelemetry.io/otel/log"
	"go.opentelemetry.io/otel/trace"
)

func NewChangeset(ctx context.Context, before, after dagql.ObjectResult[*Directory]) (*Changeset, error) {
	return &Changeset{
		Before: before,
		After:  after,
	}, nil
}

type ChangesetPaths struct {
	Added      []string
	Modified   []string
	Removed    []string
	AllRemoved []string
}

// ComputePaths computes the added, modified, and removed paths using git diff.
// This must be called from a dagql resolver context where buildkit session is available.
func (ch *Changeset) ComputePaths(ctx context.Context) (*ChangesetPaths, error) {
	if ch.Before.ID().Digest() == ch.After.ID().Digest() {
		return &ChangesetPaths{}, nil
	}

	var result *ChangesetPaths
	err := ch.withMountedDirs(ctx, func(beforeDir, afterDir string) error {
		output, err := gitDiffNameStatus(ctx, beforeDir, afterDir)
		if err != nil {
			return err
		}
		diff := parseGitDiffNameStatus(output, beforeDir, afterDir)

		beforeDirs, err := collectDirectories(beforeDir)
		if err != nil {
			return fmt.Errorf("collect before directories: %w", err)
		}
		afterDirs, err := collectDirectories(afterDir)
		if err != nil {
			return fmt.Errorf("collect after directories: %w", err)
		}
		addedDirs, removedDirs := diffDirectories(beforeDirs, afterDirs)

		var allRemoved []string
		allRemoved = append(allRemoved, diff.Removed...)
		allRemoved = append(allRemoved, removedDirs...)

		result = &ChangesetPaths{
			Added:      append(diff.Added, addedDirs...),
			Modified:   diff.Modified,
			Removed:    rollupRemovedPaths(allRemoved),
			AllRemoved: allRemoved,
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

// withMountedDirs mounts the before and after directories and calls fn with their paths.
// This is used by IsEmpty and AsPatch which are called through dagql with proper context.
func (ch *Changeset) withMountedDirs(ctx context.Context, fn func(beforeDir, afterDir string) error) error {
	beforeRef, err := getRefOrEvaluate(ctx, ch.Before.Self())
	if err != nil {
		return fmt.Errorf("evaluate before: %w", err)
	}

	afterRef, err := getRefOrEvaluate(ctx, ch.After.Self())
	if err != nil {
		return fmt.Errorf("evaluate after: %w", err)
	}

	bkSessionGroup, ok := buildkit.CurrentBuildkitSessionGroup(ctx)
	if !ok {
		return fmt.Errorf("no buildkit session group in context")
	}

	return MountRef(ctx, beforeRef, bkSessionGroup, func(beforeMount string, _ *mount.Mount) error {
		beforeDir, err := containerdfs.RootPath(beforeMount, ch.Before.Self().Dir)
		if err != nil {
			return err
		}

		return MountRef(ctx, afterRef, bkSessionGroup, func(afterMount string, _ *mount.Mount) error {
			afterDir, err := containerdfs.RootPath(afterMount, ch.After.Self().Dir)
			if err != nil {
				return err
			}

			err = fn(beforeDir, afterDir)
			return err
		}, mountRefAsReadOnly)
	}, mountRefAsReadOnly)
}

// IsEmpty returns true if there are no changes between before and after.
// Uses `git diff --quiet` which is fast because it exits on first difference found.
func (ch *Changeset) IsEmpty(ctx context.Context) (bool, error) {
	if ch.Before.ID().Digest() == ch.After.ID().Digest() {
		return true, nil
	}

	var isEmpty bool
	err := ch.withMountedDirs(ctx, func(beforeDir, afterDir string) error {
		var err error
		isEmpty, err = gitDiffQuiet(ctx, beforeDir, afterDir)
		return err
	})

	return isEmpty, err
}

type Changeset struct {
	Before dagql.ObjectResult[*Directory] `field:"true" doc:"The older/lower snapshot to compare against."`
	After  dagql.ObjectResult[*Directory] `field:"true" doc:"The newer/upper snapshot."`
}

func (*Changeset) Type() *ast.Type {
	return &ast.Type{
		NamedType: "Changeset",
		NonNull:   true,
	}
}

func (*Changeset) TypeDescription() string {
	return "A comparison between two directories representing changes that can be applied."
}

var _ Evaluatable = (*Changeset)(nil)

func (ch *Changeset) Evaluate(context.Context) (*buildkit.Result, error) {
	return nil, nil
}

var _ HasPBDefinitions = (*Changeset)(nil)

func (ch *Changeset) PBDefinitions(ctx context.Context) ([]*pb.Definition, error) {
	beforeDefs, err := ch.Before.Self().PBDefinitions(ctx)
	if err != nil {
		return nil, err
	}
	afterDefs, err := ch.After.Self().PBDefinitions(ctx)
	if err != nil {
		return nil, err
	}
	return append(beforeDefs, afterDefs...), nil
}

const ChangesetPatchFilename = "diff.patch"

// AsPatch generates a git-compatible patch file of all changes.
// Uses a single `git diff` command on the entire directory tree instead of
// running git diff per file, which is significantly faster.
func (ch *Changeset) AsPatch(ctx context.Context) (*File, error) {
	beforeRef, err := getRefOrEvaluate(ctx, ch.Before.Self())
	if err != nil {
		return nil, err
	}

	afterRef, err := getRefOrEvaluate(ctx, ch.After.Self())
	if err != nil {
		return nil, err
	}

	bkSessionGroup, ok := buildkit.CurrentBuildkitSessionGroup(ctx)
	if !ok {
		return nil, fmt.Errorf("no buildkit session group in context")
	}

	query, err := CurrentQuery(ctx)
	if err != nil {
		return nil, err
	}

	opt, ok := buildkit.CurrentOpOpts(ctx)
	if !ok {
		return nil, fmt.Errorf("no buildkit opts in context")
	}
	ctx = trace.ContextWithSpanContext(ctx, opt.CauseCtx)
	stdio := telemetry.SpanStdio(ctx, InstrumentationLibrary, log.Bool(telemetry.LogsVerboseAttr, true))
	defer stdio.Close()

	newRef, err := query.BuildkitCache().New(ctx, nil, bkSessionGroup,
		bkcache.WithRecordType(bkclient.UsageRecordTypeRegular),
		bkcache.WithDescription("Changeset.asPatch"))
	if err != nil {
		return nil, err
	}

	err = MountRef(ctx, beforeRef, bkSessionGroup, func(beforeMount string, _ *mount.Mount) error {
		beforeDir, err := containerdfs.RootPath(beforeMount, ch.Before.Self().Dir)
		if err != nil {
			return err
		}

		return MountRef(ctx, afterRef, bkSessionGroup, func(afterMount string, _ *mount.Mount) error {
			afterDir, err := containerdfs.RootPath(afterMount, ch.After.Self().Dir)
			if err != nil {
				return err
			}

			return MountRef(ctx, newRef, bkSessionGroup, func(root string, _ *mount.Mount) error {
				beforeMount := filepath.Join(root, "a")
				afterMount := filepath.Join(root, "b")
				if err := os.Mkdir(beforeMount, 0755); err != nil {
					return err
				}
				defer os.RemoveAll(beforeMount)
				if err := os.Mkdir(afterMount, 0755); err != nil {
					return err
				}
				defer os.RemoveAll(afterMount)
				if err := syscall.Mount(beforeDir, beforeMount, "", syscall.MS_BIND, ""); err != nil {
					return fmt.Errorf("bind mount before to a/: %w", err)
				}
				defer syscall.Unmount(beforeMount, syscall.MNT_DETACH)
				if err := syscall.Mount(afterDir, afterMount, "", syscall.MS_BIND, ""); err != nil {
					return fmt.Errorf("bind mount after to b/: %w", err)
				}
				defer syscall.Unmount(afterMount, syscall.MNT_DETACH)

				patchFile, err := os.Create(filepath.Join(root, ChangesetPatchFilename))
				if err != nil {
					return err
				}
				defer patchFile.Close()

				cmd := exec.Command("git", "diff", "--no-index", "--src-prefix=", "--dst-prefix=", "a", "b")
				cmd.Dir = root
				cmd.Stdout = io.MultiWriter(patchFile, stdio.Stdout)
				cmd.Stderr = stdio.Stderr

				if err := cmd.Run(); err != nil {
					var exitErr *exec.ExitError
					if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
						// Exit code 1 means differences found - expected
					} else {
						return fmt.Errorf("git diff: %w", err)
					}
				}

				return nil
			})
		}, mountRefAsReadOnly)
	}, mountRefAsReadOnly)

	if err != nil {
		return nil, err
	}

	snap, err := newRef.Commit(ctx)
	if err != nil {
		return nil, err
	}

	return &File{
		Result:   snap,
		File:     ChangesetPatchFilename,
		Platform: query.Platform(),
	}, nil
}

func (ch *Changeset) Export(ctx context.Context, destPath string) (rerr error) {
	paths, err := ch.ComputePaths(ctx)
	if err != nil {
		return fmt.Errorf("compute paths: %w", err)
	}

	dir, err := ch.Before.Self().Diff(ctx, ch.After.Self())
	if err != nil {
		return err
	}

	query, err := CurrentQuery(ctx)
	if err != nil {
		return err
	}
	bk, err := query.Buildkit(ctx)
	if err != nil {
		return fmt.Errorf("failed to get buildkit client: %w", err)
	}

	ctx, span := Tracer(ctx).Start(ctx, fmt.Sprintf("export changeset to host %s", destPath))
	defer telemetry.EndWithCause(span, &rerr)

	root, closer, err := mountObj(ctx, dir)
	if err != nil {
		return fmt.Errorf("failed to mount directory: %w", err)
	}
	defer closer(false)

	root, err = containerdfs.RootPath(root, dir.Dir)
	if err != nil {
		return err
	}

	return bk.LocalDirExport(ctx, root, destPath, true, paths.Removed)
}
