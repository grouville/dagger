# Dirty Detection Regression Investigation

## TL;DR

`dagger call -m version dirty` returns `true` on a clean repo. Root cause: the `Changes()` API doesn't understand gitignore semantics, and Dagger's gitignore filter doesn't read global git config.

## Context

| PR | Description |
|----|-------------|
| #11232 | Simplified module version - original working implementation |
| #11580 | Lazy changeset API - introduced the regression |
| #11241 | Git repo dirty detection |
| #11326 | Uncommitted changes detection |

Branch: `fix-module-version`

## Repro

```bash
git status --porcelain          # empty (clean)
./hack/with-dev dagger call -m version dirty   # returns true (wrong)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        version/main.go                          │
│                                                                 │
│  Dirty() ─────► Changes().IsEmpty() ─────► BROKEN              │
│     │                                                           │
│     │           (doesn't understand gitignore)                  │
│     │                                                           │
│     └──────────► git status --porcelain ─────► WORKS           │
│                  (in container)                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     core/git_local.go                           │
│                                                                 │
│  Cleaned() ── git restore --staged . ──┐                       │
│            ── git restore .          ──┼──► cleaned directory  │
│            ── git clean -fd          ──┘                       │
│                                                                 │
│  Dirty() ───► raw directory (includes gitignored files)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               util/fsxutil/gitignore_matcher.go                 │
│                                                                 │
│  getGitIgnorePatterns() ─► reads .gitignore files in tree      │
│                          ─► does NOT read ~/.config/git/ignore │
│                          ─► does NOT read core.excludesFile    │
└─────────────────────────────────────────────────────────────────┘
```

## What Changed

**Before (working):**
```go
func (v Version) Dirty(ctx context.Context) (bool, error) {
    checkout := v.Git.Head().Tree()
    checkout = checkout.WithDirectory("", v.Inputs)
    status, err := dag.Container().
        From("alpine/git:latest").
        WithMountedDirectory(".", checkout).
        WithExec([]string{"git", "status", "--porcelain"}).
        Stdout(ctx)
    return strings.TrimSpace(status) != "", nil
}
```

**After (broken):**
```go
func (v Version) Dirty(ctx context.Context) (bool, error) {
    checkout := v.Git.Head().Tree()
    changes := v.Inputs.Changes(checkout)
    isEmpty, err := changes.IsEmpty(ctx)
    return !isEmpty, nil
}
```

## Debug Functions

```bash
# Each returns structured info about dirty state
./hack/with-dev dagger call -m version debug-dirty-info              # current impl
./hack/with-dev dagger call -m version debug-dirty-git-status        # git status in container
./hack/with-dev dagger call -m version debug-dirty-overlay           # overlay + Changes()
./hack/with-dev dagger call -m version debug-dirty-overlay-filtered  # overlay with Filter()
./hack/with-dev dagger call -m version debug-git-uncommitted         # Uncommitted() API
```

## Observed Behavior

| Approach | Result | Files Detected |
|----------|--------|----------------|
| `git status` (local) | clean | none |
| `Changes().IsEmpty()` | dirty | gitignored files |
| `git status` (container) | dirty | `.uv-cache/` (missing .gitignore) |
| `Filter(gitignore: true)` | dirty | `.claude/settings.local.json` |
| `Uncommitted()` | dirty | 1243 files |

Sample false positives:
```
.claude/settings.local.json    # in global gitignore only
.pytest_cache/                 # internal .gitignore, but dir appears
.ruff_cache/                   
sdk/python/.uv-cache/          # .gitignore excluded by **/.git* pattern
```

## Root Causes

1. **`Changes()` API is gitignore-unaware**: It compares directory contents byte-for-byte with no concept of ignored files.

2. **`+ignore` patterns don't match gitignore**: The version module uses `+ignore=["**/.git*", ...]` which inadvertently excludes `.gitignore` files themselves.

3. **Dagger's gitignore filter is incomplete**: `Directory.Filter(gitignore: true)` only reads `.gitignore` files in the tree. It doesn't read:
   - `~/.config/git/ignore`
   - `~/.gitignore`  
   - `git config --global core.excludesFile`

4. **Empty directories**: Git doesn't track empty directories, but they exist in the working tree and show up as additions.

## Fix Options

### Option A: Container-based git status (pragmatic)

Revert to running `git status --porcelain` in container. Pros: works. Cons: requires container, slower.

```go
func (v Version) Dirty(ctx context.Context) (bool, error) {
    checkout := v.Git.Head().Tree()
    combined := checkout.WithDirectory("", v.Inputs)
    status, err := dag.Container().
        From("alpine/git:latest").
        WithMountedDirectory(".", combined).
        WithExec([]string{"git", "status", "--porcelain"}).
        Stdout(ctx)
    return strings.TrimSpace(status) != "", nil
}
```

**Status**: Implemented, still returning dirty. Need to debug why.

### Option B: Fix gitignore_matcher.go (engine change)

Modify `util/fsxutil/gitignore_matcher.go` to read global git config:

```go
// In getGitIgnorePatterns(), also read:
// 1. git config --global core.excludesFile
// 2. ~/.config/git/ignore (XDG default)
```

### Option C: New API in engine

Add `GitRepository.IsDirty()` that runs git status internally and returns bool.

## Key Files

| File | Purpose |
|------|---------|
| `version/main.go:132-145` | `Dirty()` implementation |
| `version/main.go:313-335` | `DebugDirtyGitStatus()` helper |
| `version/main.go:584-625` | `DebugDirtyOverlayFiltered()` helper |
| `core/git_local.go:88-212` | `Cleaned()` implementation |
| `core/schema/git.go:717-766` | `uncommitted()` changeset |
| `util/fsxutil/gitignore_matcher.go` | gitignore pattern matching |

---

# Full Source Code Reference

## version/main.go (current Dirty + debug helpers)

```go
func (v Version) Dirty(ctx context.Context) (bool, error) {
	checkout := v.Git.Head().Tree()
	combined := checkout.WithDirectory("", v.Inputs)
	status, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".", combined).
		WithExec([]string{"git", "status", "--porcelain"}).
		Stdout(ctx)
	if err != nil {
		return false, err
	}
	return strings.TrimSpace(status) != "", nil
}

// DebugDirtyInfo returns detailed information about the dirty detection state (current broken impl)
func (v Version) DebugDirtyInfo(ctx context.Context) (*DebugInfo, error) {
	checkout := v.Git.Head().Tree()
	changes := v.Inputs.Changes(checkout)

	isEmpty, err := changes.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	added, err := changes.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get added paths: %w", err)
	}

	modified, err := changes.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get modified paths: %w", err)
	}

	removed, err := changes.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get removed paths: %w", err)
	}

	inputsDigest, err := v.Inputs.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get inputs digest: %w", err)
	}

	checkoutDigest, err := checkout.Digest(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get checkout digest: %w", err)
	}

	return &DebugInfo{
		IsDirty:        !isEmpty,
		AddedPaths:     added,
		ModifiedPaths:  modified,
		RemovedPaths:   removed,
		InputsDigest:   inputsDigest,
		CheckoutDigest: checkoutDigest,
	}, nil
}

// DebugDirtyGitStatus returns dirty state using git status (respects .gitignore)
func (v Version) DebugDirtyGitStatus(ctx context.Context) (*DebugGitStatusInfo, error) {
	checkout := v.Git.Head().Tree()
	combined := checkout.WithDirectory("", v.Inputs)
	status, err := dag.Container().
		From("alpine/git:latest").
		WithWorkdir("/src").
		WithMountedDirectory(".", combined).
		WithExec([]string{"git", "status", "--porcelain"}).
		Stdout(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to run git status: %w", err)
	}
	status = strings.TrimSpace(status)
	var changedFiles []string
	if status != "" {
		changedFiles = strings.Split(status, "\n")
	}
	return &DebugGitStatusInfo{
		IsDirty:      status != "",
		GitStatus:    status,
		ChangedFiles: changedFiles,
	}, nil
}

// DebugDirtyOverlayFiltered uses overlay approach: cleaned tree + source overlay
func (v Version) DebugDirtyOverlayFiltered(
	ctx context.Context,
	// Full repo for gitignore context
	// +defaultPath="/"
	// +ignore=["**/.dagger"]
	source *dagger.Directory,
) (*DebugGitStatusInfo, error) {
	gitRepo := source.AsGit()
	cleaned := gitRepo.Head().Tree()
	sourceNoGit := source.Filter(dagger.DirectoryFilterOpts{
		Exclude: []string{".git"},
	})
	combined := cleaned.WithDirectory("", sourceNoGit)
	changes := combined.Changes(cleaned)

	isEmpty, err := changes.IsEmpty(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check isEmpty: %w", err)
	}

	var changedFiles []string
	if !isEmpty {
		added, _ := changes.AddedPaths(ctx)
		modified, _ := changes.ModifiedPaths(ctx)
		removed, _ := changes.RemovedPaths(ctx)
		for _, p := range added {
			changedFiles = append(changedFiles, "A  "+p)
		}
		for _, p := range modified {
			changedFiles = append(changedFiles, "M  "+p)
		}
		for _, p := range removed {
			changedFiles = append(changedFiles, "D  "+p)
		}
	}

	return &DebugGitStatusInfo{
		IsDirty:      !isEmpty,
		GitStatus:    strings.Join(changedFiles, "\n"),
		ChangedFiles: changedFiles,
	}, nil
}

type DebugGitStatusInfo struct {
	IsDirty      bool
	GitStatus    string
	ChangedFiles []string
}

type DebugInfo struct {
	IsDirty        bool
	AddedPaths     []string
	ModifiedPaths  []string
	RemovedPaths   []string
	InputsDigest   string
	CheckoutDigest string
}
```

## core/git_local.go (Cleaned implementation)

```go
func (repo *LocalGitRepository) Dirty(ctx context.Context) (inst dagql.ObjectResult[*Directory], rerr error) {
	return repo.Directory, nil
}

func (repo *LocalGitRepository) Cleaned(ctx context.Context) (inst dagql.ObjectResult[*Directory], rerr error) {
	srv := dagql.CurrentDagqlServer(ctx)
	query, err := CurrentQuery(ctx)
	if err != nil {
		return inst, err
	}
	bk, err := query.Buildkit(ctx)
	if err != nil {
		return inst, err
	}
	cache := query.BuildkitCache()

	bkSessionGroup, ok := buildkit.CurrentBuildkitSessionGroup(ctx)
	if !ok {
		return inst, fmt.Errorf("no buildkit session group in context")
	}

	llb := repo.Directory.Self().LLB
	res, err := bk.Solve(ctx, bkgw.SolveRequest{Definition: llb})
	if err != nil {
		return inst, err
	}
	ref, err := res.SingleRef()
	if err != nil {
		return inst, err
	}
	parent, err := ref.CacheRef(ctx)
	if err != nil {
		return inst, err
	}

	bkref, err := cache.New(ctx, parent, bkSessionGroup,
		bkcache.CachePolicyRetain,
		bkcache.WithRecordType(bkclient.UsageRecordTypeRegular),
		bkcache.WithDescription("git cleaned worktree"))

	if err != nil {
		return inst, err
	}
	defer func() {
		if rerr != nil && bkref != nil {
			bkref.Release(context.WithoutCancel(ctx))
		}
	}()
	skip := false
	err = MountRef(ctx, bkref, bkSessionGroup, func(parentRoot string, _ *mount.Mount) error {
		src, err := fs.RootPath(parentRoot, repo.Directory.Self().Dir)
		if err != nil {
			return err
		}

		git := gitutil.NewGitCLI(gitutil.WithDir(src))
		worktree, err := git.WorkTree(ctx)
		if err != nil {
			return err
		}
		if worktree == "" {
			skip = true // no worktree, no changes
			return nil
		}
		gitDir, err := git.GitDir(ctx)
		if err != nil {
			return err
		}

		idx, err := os.Open(filepath.Join(gitDir, "index"))
		if err != nil {
			return err
		}
		defer idx.Close()

		// NOTE: apply the index to a temp file because "git restore --staged"
		// re-writes the index which we don't want to show up as a changed file
		// in the final result
		tmp, err := os.CreateTemp("", "dagger-git-index-")
		if err != nil {
			return err
		}
		_, err = io.Copy(tmp, idx)
		if err != nil {
			tmp.Close()
			return err
		}
		if err := tmp.Close(); err != nil {
			return err
		}
		defer os.Remove(tmp.Name())

		git = git.New(gitutil.WithIndexFile(tmp.Name()))

		// reset index to HEAD
		// NOTE: we cannot use "git reset --hard" because it writes every file,
		// which *kills* performance on overlayfs
		_, err = git.Run(ctx, "restore", "--staged", ".")
		if err != nil {
			return err
		}
		_, err = git.Run(ctx, "restore", ".")
		if err != nil {
			return err
		}
		_, err = git.Run(ctx, "clean", "-fd")
		if err != nil {
			return err
		}

		return nil
	})
	if err != nil {
		return inst, err
	}
	if skip {
		return repo.Directory, nil
	}

	dir := NewDirectory(nil, repo.Directory.Self().Dir, query.Platform(), nil)
	snap, err := bkref.Commit(ctx)
	if err != nil {
		return inst, err
	}
	bkref = nil
	dir.Result = snap

	return dagql.NewObjectResultForCurrentID(ctx, srv, dir)
}
```

## core/schema/git.go (uncommitted implementation)

```go
func (s *gitSchema) uncommitted(ctx context.Context, parent dagql.ObjectResult[*core.GitRepository], args struct{}) (inst dagql.ObjectResult[*core.Changeset], _ error) {
	dag, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return inst, err
	}

	var cleaned dagql.ObjectResult[*core.Directory]
	var dirty dagql.ObjectResult[*core.Directory]

	dirty, err = parent.Self().Backend.Dirty(ctx)
	if err != nil {
		return inst, err
	}
	if dirty.Self() == nil {
		// clean repo, so just get head, there'll be no diff later
		if err := dag.Select(ctx, parent, &dirty,
			dagql.Selector{
				Field: "head",
			},
			dagql.Selector{
				Field: "tree",
			},
		); err != nil {
			return inst, fmt.Errorf("failed to select head tree for clean repo: %w", err)
		}
		cleaned = dirty
	} else {
		// wrapped in an internal field to get good caching behavior
		if err := dag.Select(ctx, parent, &cleaned, dagql.Selector{
			Field: "__cleaned",
		}); err != nil {
			return inst, fmt.Errorf("failed to select cleaned: %w", err)
		}
	}

	if err := dag.Select(ctx, dirty, &inst,
		dagql.Selector{
			Field: "changes",
			Args: []dagql.NamedInput{
				{
					Name:  "from",
					Value: dagql.NewID[*core.Directory](cleaned.ID()),
				},
			},
		},
	); err != nil {
		return inst, fmt.Errorf("failed to select cleaned digest: %w", err)
	}
	return inst, nil
}
```

## core/changeset.go (IsEmpty and path comparison)

```go
func NewChangeset(ctx context.Context, before, after dagql.ObjectResult[*Directory]) (*Changeset, error) {
	return &Changeset{
		Before:    before,
		After:     after,
		pathsOnce: &sync.Once{},
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
	ch.pathsOnce.Do(func() {
		ch.cachedPaths, ch.pathsErr = ch.computePathsOnce(ctx)
	})
	return ch.cachedPaths, ch.pathsErr
}

func (ch *Changeset) computePathsOnce(ctx context.Context) (*ChangesetPaths, error) {
	if ch.Before.ID().Digest() == ch.After.ID().Digest() {
		return &ChangesetPaths{}, nil
	}

	var result *ChangesetPaths
	err := ch.withMountedDirs(ctx, func(beforeDir, afterDir string) error {
		fileChanges, err := compareDirectories(ctx, beforeDir, afterDir)
		if err != nil {
			return err
		}

		beforeDirs, err := listSubdirectories(beforeDir)
		if err != nil {
			return fmt.Errorf("list before directories: %w", err)
		}
		afterDirs, err := listSubdirectories(afterDir)
		if err != nil {
			return fmt.Errorf("list after directories: %w", err)
		}
		addedDirs, removedDirs := diffStringSlices(beforeDirs, afterDirs)

		allRemoved := slices.Concat(fileChanges.Removed, removedDirs)

		result = &ChangesetPaths{
			Added:      slices.Concat(fileChanges.Added, addedDirs),
			Modified:   fileChanges.Modified,
			Removed:    collapseChildPaths(allRemoved),
			AllRemoved: allRemoved,
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

type Changeset struct {
	Before dagql.ObjectResult[*Directory] `field:"true" doc:"The older/lower snapshot to compare against."`
	After  dagql.ObjectResult[*Directory] `field:"true" doc:"The newer/upper snapshot."`

	pathsOnce   *sync.Once
	cachedPaths *ChangesetPaths
	pathsErr    error
}

func (ch *Changeset) IsEmpty(ctx context.Context) (bool, error) {
	if ch.Before.ID().Digest() == ch.After.ID().Digest() {
		return true, nil
	}

	var isEmpty bool
	err := ch.withMountedDirs(ctx, func(beforeDir, afterDir string) error {
		identical, err := directoriesAreIdentical(ctx, beforeDir, afterDir)
		if err != nil {
			return err
		}
		isEmpty = identical
		return nil
	})
	if err != nil {
		return false, err
	}
	return isEmpty, nil
}
```

## util/fsxutil/gitignore_matcher.go (gitignore implementation - THE PROBLEM)

```go
type GitignoreMatcher struct {
	fs fsutil.FS

	// Cache for parsed gitignore files to avoid re-reading
	gitignoreCache         map[string]gitignore.Matcher
	gitignoreCachePatterns map[string][]gitignore.Pattern
	gitignoreCacheMu       sync.RWMutex
}

// NewGitIgnoreMatcher creates a new GitignoreMatcher for the given FS
func NewGitIgnoreMatcher(fs fsutil.FS) *GitignoreMatcher {
	gfs := &GitignoreMatcher{
		fs:                     fs,
		gitignoreCache:         make(map[string]gitignore.Matcher),
		gitignoreCachePatterns: make(map[string][]gitignore.Pattern),
	}
	return gfs
}

// Matches checks if a path should be ignored based on gitignore rules
func (gfs *GitignoreMatcher) Matches(path string, isDir bool) (out bool, _ error) {
	// Clean the path and ensure it's relative
	path = filepath.Clean(path)
	if filepath.IsAbs(path) {
		path = strings.TrimPrefix(path, "/")
	}

	// Get the directory containing this path
	var dirPath string
	if isDir {
		dirPath = path
	} else {
		dirPath = filepath.Dir(path)
		if dirPath == "." && path != "." {
			dirPath = ""
		}
	}

	// Get all accumulated patterns for this directory
	matcher, err := gfs.getGitIgnoreMatcher(dirPath)
	if err != nil {
		return false, err
	}
	if matcher == nil {
		// No patterns found, nothing to ignore
		return false, nil
	}

	pathComponents := strings.Split(path, string(filepath.Separator))
	return matcher.Match(pathComponents, isDir), nil
}

func (gfs *GitignoreMatcher) getGitIgnorePatterns(dirPath string) (patterns []gitignore.Pattern, rerr error) {
	if dirPath == "" {
		dirPath = "."
	}

	gfs.gitignoreCacheMu.RLock()
	if patterns, exists := gfs.gitignoreCachePatterns[dirPath]; exists {
		gfs.gitignoreCacheMu.RUnlock()
		return patterns, nil
	}
	gfs.gitignoreCacheMu.RUnlock()

	defer func() {
		if rerr == nil {
			gfs.gitignoreCacheMu.Lock()
			gfs.gitignoreCachePatterns[dirPath] = patterns
			gfs.gitignoreCacheMu.Unlock()
		}
	}()

	if dirPath != "." {
		parentDir := filepath.Dir(dirPath)
		var err error
		patterns, err = gfs.getGitIgnorePatterns(parentDir)
		if err != nil {
			return nil, err
		}
	}

	// ⚠️  THIS IS THE PROBLEM - only reads .gitignore files in the tree
	// Does NOT read:
	//   - ~/.config/git/ignore
	//   - ~/.gitignore
	//   - git config --global core.excludesFile
	gitignorePath := filepath.Join(dirPath, ".gitignore")
	reader, err := gfs.fs.Open(gitignorePath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return patterns, nil
		}
		return nil, err
	}
	defer reader.Close()

	// Parse the .gitignore file
	domain := strings.Split(dirPath, string(filepath.Separator))
	if dirPath == "." {
		domain = nil
	}

	// Read patterns from the .gitignore filepath
	newPatterns, err := parseGitIgnoreFile(reader, domain)
	if err != nil {
		return nil, err
	}
	patterns = slices.Clone(patterns)
	patterns = append(patterns, newPatterns...)

	return patterns, nil
}

// parseGitIgnoreFile parses a gitignore file and returns patterns
func parseGitIgnoreFile(reader io.Reader, domain []string) ([]gitignore.Pattern, error) {
	var patterns []gitignore.Pattern
	scanner := bufio.NewScanner(reader)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			// skip empty lines and comments
			continue
		}
		pattern := gitignore.ParsePattern(line, domain)
		patterns = append(patterns, pattern)
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return patterns, nil
}
```

## Next Steps

1. Debug why container-based `git status` is still showing dirty after fix
2. Check if `.gitignore` files are being properly included (not excluded by `**/.git*`)
3. Consider engine-level fix to gitignore implementation
4. Alternatively, add explicit `IsDirty()` API to GitRepository that shells out to git
