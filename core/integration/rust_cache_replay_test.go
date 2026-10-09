package core

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"

	"dagger.io/dagger"
	"dagger.io/dagger/engineconn"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/hack/rust-cache/model"
	"github.com/dagger/dagger/hack/rust-cache/replay"
	"github.com/dagger/dagger/internal/buildkit/identity"
	"github.com/dagger/dagger/internal/testutil"
	"github.com/dagger/dagger/internal/version"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

// TestRustCompilerReplay exercises the same graph builder as rcexp, including
// selective invalidation and filesystem-only reuse on a second fresh engine.
func (RemoteCacheTransferSuite) TestRustCompilerReplay(ctx context.Context, t *testctx.T) {
	outer := connect(ctx, t, dagger.WithVersionOverride(version.Version(version.WithV())))
	start := func(volume *dagger.CacheVolume) *dagger.Client {
		ctr := devEngineContainerWithStateKey(outer, "rust-replay-state-"+identity.NewID(), func(ctr *dagger.Container) *dagger.Container {
			return ctr.WithMountedCache("/transfer-fixture", volume).WithEnvVariable("_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT", "/transfer-fixture")
		})
		ctr = engineWithConfig(ctx, t, engineConfigWithEnabled(true), engineConfigWithGC("1000000000000000", "0", "1000000000000000", "0"))(ctr)
		upstream := devEngineContainerAsService(ctr)
		tunnel, err := outer.Host().Tunnel(upstream).Start(ctx)
		require.NoError(t, err)
		endpoint, err := tunnel.Endpoint(ctx, dagger.ServiceEndpointOpts{Scheme: "tcp"})
		require.NoError(t, err)
		// Bypass the test runner's inherited session so A and B really have
		// separate caches. Remove transport credentials only in the child CLI.
		conn, found, err := engineconn.FromLocalCLI(ctx, &engineconn.Config{
			RunnerHost: endpoint, Workdir: t.TempDir(), VersionOverride: version.Version(version.WithV()),
			LogOutput: testutil.NewTWriter(t), UnsetEnv: []string{"DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"},
		})
		require.NoError(t, err)
		require.True(t, found, "set _EXPERIMENTAL_DAGGER_CLI_BIN to the from-source CLI")
		client, err := dagger.Connect(ctx, dagger.WithConn(conn))
		require.NoError(t, err)
		t.Cleanup(func() { require.NoError(t, stopNestedEngine(ctx, &client, &upstream, &tunnel)) })
		return client
	}
	aVolume := outer.CacheVolume("rust-replay-a-" + identity.NewID())
	bVolume := outer.CacheVolume("rust-replay-b-" + identity.NewID())
	a, b := start(aVolume), start(bVolume)
	source, err := replay.Fixture()
	require.NoError(t, err)
	// Keep the compiler replay and cross-engine transfer on the larger-tree
	// path too. These resources leave the fixture's executable unchanged.
	for i := range 80 {
		source[fmt.Sprintf("app/resources/%02d.txt", i)] = replay.SourceFile{Contents: fmt.Sprintf("resource %d\n", i), Mode: 0644}
	}
	// Exercise the larger source tree with repeated basenames, nested paths,
	// empty/UTF-8 contents and mixed permissions. Export checks the filesystem
	// independently of the recipe layout; prior snapshots must stay immutable.
	many := replay.Source{}
	for i := range 80 {
		many[fmt.Sprintf("nested/%02d/resource.txt", i)] = replay.SourceFile{Contents: fmt.Sprintf("file %d\n", i), Mode: 0644}
	}
	many["empty.txt"] = replay.SourceFile{Contents: "", Mode: 0600}
	many["space dir/run.sh"] = replay.SourceFile{Contents: "#!/bin/sh\nprintf 'héllo\\n'\n", Mode: 0751}
	originalDirectory := many.Directory(a)
	checkSource := func(directory *dagger.Directory, expected replay.Source) {
		root := t.TempDir()
		_, err := directory.Export(ctx, root)
		require.NoError(t, err)
		count := 0
		err = filepath.WalkDir(root, func(filename string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil || entry.IsDir() {
				return walkErr
			}
			name, err := filepath.Rel(root, filename)
			require.NoError(t, err)
			file, present := expected[filepath.ToSlash(name)]
			require.True(t, present, name)
			contents, err := os.ReadFile(filename)
			require.NoError(t, err)
			require.Equal(t, file.Contents, string(contents), name)
			info, err := entry.Info()
			require.NoError(t, err)
			require.Equal(t, os.FileMode(file.Mode), info.Mode().Perm(), name)
			count++
			return nil
		})
		require.NoError(t, err)
		require.Equal(t, len(expected), count)
	}
	checkSource(originalDirectory, many)
	// Native inputs preserve modes and nested-package ownership. Build-state
	// directories must be excluded before projecting the package roots.
	nativeRoot := t.TempDir()
	owned := replay.Source{
		"Cargo.toml":            {Contents: "workspace", Mode: 0644},
		"app/src/main.rs":       {Contents: "app", Mode: 0664},
		"app/nested/src/lib.rs": {Contents: "nested", Mode: 0600},
		"app2/src/lib.rs":       {Contents: "sibling", Mode: 0751},
		"app/target/binary":     {Contents: "excluded build state", Mode: 0600},
		".git/config":           {Contents: "excluded git state", Mode: 0600},
	}
	for name, file := range owned {
		filename := filepath.Join(nativeRoot, name)
		require.NoError(t, os.MkdirAll(filepath.Dir(filename), 0755))
		require.NoError(t, os.WriteFile(filename, []byte(file.Contents), os.FileMode(file.Mode)))
		require.NoError(t, os.Chmod(filename, os.FileMode(file.Mode)))
	}
	packages := []model.Package{{Root: "/src"}, {Root: "/src/app"}, {Root: "/src/app/nested"}, {Root: "/src/app2"}}
	projections := replay.PackageDirectories(a.Host().Directory(nativeRoot, dagger.HostDirectoryOpts{Exclude: []string{"**/.git", "**/target"}}), packages)
	for root, expected := range map[string]replay.Source{
		"/src":            {"Cargo.toml": owned["Cargo.toml"]},
		"/src/app":        {"src/main.rs": owned["app/src/main.rs"]},
		"/src/app/nested": {"src/lib.rs": owned["app/nested/src/lib.rs"]},
		"/src/app2":       {"src/lib.rs": owned["app2/src/lib.rs"]},
	} {
		checkSource(projections[root], expected)
	}
	editedSource := cloneRustSource(many)
	editedSource["nested/00/resource.txt"] = replay.SourceFile{Contents: "edited\n", Mode: 0600}
	checkSource(editedSource.Directory(a), editedSource)
	checkSource(originalDirectory, many)
	wrapperPath := filepath.Join(t.TempDir(), "rustc-wrapper")
	build := exec.CommandContext(ctx, "go", "build", "-trimpath", "-o", wrapperPath, "./hack/rust-cache/wrapper")
	build.Dir = "../.."
	build.Env = append(os.Environ(), "CGO_ENABLED=0", "GOOS=linux", "GOARCH=amd64")
	output, err := build.CombinedOutput()
	require.NoError(t, err, string(output))
	wrapper := a.Host().File(wrapperPath)
	plan, err := replay.Capture(ctx, a, source, replay.CaptureOptions{Wrapper: wrapper})
	require.NoError(t, err)
	require.Len(t, plan.Actions, 4)
	evaluate := func(client *dagger.Client, plan *model.Plan, source replay.Source) (*replay.Graph, *replay.Report) {
		graph, err := replay.Build(client, plan, source)
		require.NoError(t, err)
		report, err := graph.Evaluate(ctx, 4)
		require.NoError(t, err)
		return graph, report
	}
	runBinary := func(client *dagger.Client, graph *replay.Graph, image string) string {
		for _, op := range graph.Operations {
			if op.Action.Crate != "app" {
				continue
			}
			for filename, file := range op.Files {
				if path.Ext(filename) != "" {
					continue
				}
				stdout, err := client.Container(dagger.ContainerOpts{Platform: "linux/amd64"}).From(image).WithMountedFile("/app", file).
					WithExec([]string{"/app"}, dagger.ContainerWithExecOpts{DisableDaggerInDagger: true}).Stdout(ctx)
				require.NoError(t, err)
				return stdout
			}
		}
		t.Fatal("missing application binary")
		return ""
	}
	markers := func(report *replay.Report) map[string]string {
		result := map[string]string{}
		for _, action := range report.Actions {
			result[action.Crate] = action.Execution
		}
		return result
	}
	graph, cold := evaluate(a, plan, source)
	for _, action := range cold.Actions {
		for filename, digest := range action.Digests {
			require.Equal(t, plan.BaselineDigests[filename], digest, filename)
		}
	}
	require.Equal(t, "31 default\n", runBinary(a, graph, plan.Image))
	// Force small leaves so this fixture exercises artifact-tree merges too.
	// Bounded filesystem demand must produce the same bytes as captured Cargo.
	balancedOptions := replay.BuildOptions{ArtifactLeafFiles: 2}
	balancedGraph, err := replay.BuildWithOptions(a, plan, source, balancedOptions)
	require.NoError(t, err)
	require.NoError(t, balancedGraph.DemandFilesystem(ctx, 2))
	balancedCold, err := balancedGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	for _, action := range balancedCold.Actions {
		for filename, digest := range action.Digests {
			require.Equal(t, plan.BaselineDigests[filename], digest, filename)
		}
	}
	// Check the assembled directory itself, beyond each compiler's outputs.
	flatArtifacts, err := graph.Artifacts.Digest(ctx)
	require.NoError(t, err)
	balancedArtifacts, err := balancedGraph.Artifacts.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, flatArtifacts, balancedArtifacts)
	directoryOptions := replay.BuildOptions{ArtifactDirectories: true}
	directoryGraph, err := replay.BuildWithOptions(a, plan, source, directoryOptions)
	require.NoError(t, err)
	directoryCold, err := directoryGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	for _, action := range directoryCold.Actions {
		for filename, digest := range action.Digests {
			require.Equal(t, plan.BaselineDigests[filename], digest, filename)
		}
	}
	directoryArtifacts, err := directoryGraph.Artifacts.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, flatArtifacts, directoryArtifacts)
	_, warm := evaluate(a, plan, source)
	require.Equal(t, 4, warm.Reused(cold))
	coldMarkers := markers(cold)
	appEdit := cloneRustSource(source)
	appFile := appEdit["app/src/main.rs"]
	appFile.Contents = strings.ReplaceAll(appFile.Contents, "left::value() + right::value()", "left::value() + right::value() + 1")
	appEdit["app/src/main.rs"] = appFile
	appGraph, appReport := evaluate(a, plan, appEdit)
	require.Equal(t, 3, appReport.Reused(cold))
	require.Equal(t, "32 default\n", runBinary(a, appGraph, plan.Image))
	balancedEditGraph, err := replay.BuildWithOptions(a, plan, appEdit, balancedOptions)
	require.NoError(t, err)
	require.NoError(t, balancedEditGraph.DemandFilesystem(ctx, 2))
	balancedEdit, err := balancedEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, balancedEdit.Reused(balancedCold))
	require.Equal(t, "32 default\n", runBinary(a, balancedEditGraph, plan.Image))
	directoryEditGraph, err := replay.BuildWithOptions(a, plan, appEdit, directoryOptions)
	require.NoError(t, err)
	directoryEdit, err := directoryEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, directoryEdit.Reused(directoryCold))
	require.Equal(t, "32 default\n", runBinary(a, directoryEditGraph, plan.Image))
	baseEdit := cloneRustSource(source)
	baseFile := baseEdit["base/src/lib.rs"]
	baseFile.Contents = strings.ReplaceAll(baseFile.Contents, "10", "11")
	baseEdit["base/src/lib.rs"] = baseFile
	baseGraph, baseReport := evaluate(a, plan, baseEdit)
	baseMarkers := markers(baseReport)
	require.Equal(t, coldMarkers["right"], baseMarkers["right"])
	for _, crate := range []string{"base", "left", "app"} {
		require.NotEqual(t, coldMarkers[crate], baseMarkers[crate], crate)
	}
	require.Equal(t, "32 default\n", runBinary(a, baseGraph, plan.Image))
	resourceEdit := cloneRustSource(source)
	resourceEdit["right/resource.txt"] = replay.SourceFile{Contents: "new package resource", Mode: 0644}
	_, resourceReport := evaluate(a, plan, resourceEdit)
	require.NotEqual(t, coldMarkers["right"], markers(resourceReport)["right"])
	require.Equal(t, coldMarkers["base"], markers(resourceReport)["base"])
	require.Equal(t, coldMarkers["left"], markers(resourceReport)["left"])
	delete(resourceEdit, "right/resource.txt")
	_, deletedReport := evaluate(a, plan, resourceEdit)
	require.Equal(t, 4, deletedReport.Reused(cold))
	featurePlan, err := replay.Capture(ctx, a, source, replay.CaptureOptions{Wrapper: wrapper, CargoArgs: []string{"--features", "left/extra"}})
	require.NoError(t, err)
	featureGraph, _ := evaluate(a, featurePlan, source)
	require.Equal(t, "32 default\n", runBinary(a, featureGraph, featurePlan.Image))
	envPlan, err := replay.Capture(ctx, a, source, replay.CaptureOptions{Wrapper: wrapper, Environment: map[string]string{"RCE_LABEL": "changed"}})
	require.NoError(t, err)
	envGraph, envReport := evaluate(a, envPlan, source)
	require.Equal(t, "31 changed\n", runBinary(a, envGraph, envPlan.Image))
	require.NotEqual(t, coldMarkers["right"], markers(envReport)["right"])
	require.Equal(t, coldMarkers["base"], markers(envReport)["base"])
	require.Equal(t, coldMarkers["left"], markers(envReport)["left"])
	flagsPlan, err := replay.Capture(ctx, a, source, replay.CaptureOptions{Wrapper: wrapper, Environment: map[string]string{"RUSTFLAGS": "-C opt-level=1"}})
	require.NoError(t, err)
	flagsGraph, flagsReport := evaluate(a, flagsPlan, source)
	require.Zero(t, flagsReport.Reused(cold))
	require.Equal(t, "31 default\n", runBinary(a, flagsGraph, flagsPlan.Image))
	// A workspace can have terminal crates that the app does not depend on.
	// Consolidating compiler snapshots must export those independent roots too.
	independentSource := cloneRustSource(source)
	manifest := independentSource["Cargo.toml"]
	manifest.Contents = strings.Replace(manifest.Contents, `"app"]`, `"app", "unused"]`, 1)
	independentSource["Cargo.toml"] = manifest
	lock := independentSource["Cargo.lock"]
	lock.Contents += "\n[[package]]\nname = \"unused\"\nversion = \"0.1.0\"\n"
	independentSource["Cargo.lock"] = lock
	independentSource["unused/Cargo.toml"] = replay.SourceFile{Contents: "[package]\nname = \"unused\"\nversion = \"0.1.0\"\nedition = \"2021\"\n", Mode: 0644}
	independentSource["unused/src/lib.rs"] = replay.SourceFile{Contents: "pub fn value() -> u32 { 99 }\n", Mode: 0644}
	independentPlan, err := replay.Capture(ctx, a, independentSource, replay.CaptureOptions{Wrapper: wrapper})
	require.NoError(t, err)
	require.Len(t, independentPlan.Actions, 5)
	independentGraph, err := replay.BuildWithOptions(a, independentPlan, independentSource, directoryOptions)
	require.NoError(t, err)
	for filename, expected := range independentPlan.BaselineDigests {
		actual, err := independentGraph.Artifacts.File(strings.TrimPrefix(filename, model.TargetRoot+"/")).Digest(ctx)
		require.NoError(t, err)
		require.Equal(t, expected, actual, filename)
	}
	// Preserve rustc's within-crate state as a native Directory. Seeding an
	// edited build must leave the old snapshot immutable and unrelated crate
	// results reusable. The experiment only enables incremental for the app.
	incGraph, err := replay.BuildWithOptions(a, plan, source, replay.BuildOptions{IncrementalCrate: "app", ArtifactDirectories: true})
	require.NoError(t, err)
	incCold, err := incGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	stateEntries, err := incGraph.Incremental.Entries(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, stateEntries)
	stateDigest, err := incGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	incEditGraph, err := replay.BuildWithOptions(a, plan, appEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: incGraph.Incremental, ArtifactDirectories: true})
	require.NoError(t, err)
	incEdit, err := incEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, incEdit.Reused(incCold))
	require.Equal(t, "32 default\n", runBinary(a, incEditGraph, plan.Image))
	incDepGraph, err := replay.BuildWithOptions(a, plan, baseEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: incGraph.Incremental, ArtifactDirectories: true})
	require.NoError(t, err)
	incDep, err := incDepGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 1, incDep.Reused(incCold), "only the unrelated right crate remains reusable")
	require.Equal(t, "32 default\n", runBinary(a, incDepGraph, plan.Image))
	afterSeedDigest, err := incGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, stateDigest, afterSeedDigest, "seed snapshot must remain immutable")
	// Automatic history keeps whole results independent of the seed selected
	// for a later miss. Reverting an edit must reuse the original compiler,
	// even though the latest incremental state came from the edited source.
	automaticOptions := replay.BuildOptions{SourceDirectory: source.Directory(a)}
	automaticGraph, err := replay.BuildAutomatic(ctx, a, plan, source, automaticOptions, nil)
	require.NoError(t, err)
	automaticCold, err := automaticGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	_, err = automaticGraph.History.File("manifest.json").Contents(ctx)
	require.NoError(t, err)
	historyDigest, err := automaticGraph.History.Digest(ctx)
	require.NoError(t, err)
	automaticEditGraph, err := replay.BuildAutomatic(ctx, a, plan, appEdit,
		replay.BuildOptions{SourceDirectory: appEdit.Directory(a)}, automaticGraph.History)
	require.NoError(t, err)
	automaticEdit, err := automaticEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, automaticEdit.Reused(automaticCold))
	require.Equal(t, 3, automaticEditGraph.HistoryHits)
	require.Equal(t, "32 default\n", runBinary(a, automaticEditGraph, plan.Image))
	_, err = automaticEditGraph.History.File("manifest.json").Contents(ctx)
	require.NoError(t, err)
	automaticRevertGraph, err := replay.BuildAutomatic(ctx, a, plan, source, automaticOptions, automaticEditGraph.History)
	require.NoError(t, err)
	automaticRevert, err := automaticRevertGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, automaticRevertGraph.HistoryHits)
	require.Equal(t, 4, automaticRevert.Reused(automaticCold))
	require.Equal(t, "31 default\n", runBinary(a, automaticRevertGraph, plan.Image))
	afterHistoryDigest, err := automaticGraph.History.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, historyDigest, afterHistoryDigest, "retained history must remain immutable")
	reference, err := automaticEditGraph.HistoryReference(ctx)
	require.NoError(t, err)
	loadedHistory, err := reference.Load(ctx, a)
	require.NoError(t, err)
	loadedDigest, err := loadedHistory.Digest(ctx)
	require.NoError(t, err)
	editedDigest, err := automaticEditGraph.History.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, editedDigest, loadedDigest)
	reference.ManifestDigest = strings.Repeat("0", 64)
	_, err = reference.Load(ctx, a)
	require.ErrorIs(t, err, replay.ErrHistoryUnavailable, "foreign or recycled local handles must be acceleration misses")
	// Batch misses share one execution while retaining each crate's outputs and
	// state independently. Check the edit path and reject new cross-package
	// reads, which would otherwise escape the per-package logical cache key.
	batchBinary := filepath.Join(t.TempDir(), "rcexp")
	buildBatch := exec.CommandContext(ctx, "go", "build", "-trimpath", "-o", batchBinary, "./hack/rust-cache")
	buildBatch.Dir = "../.."
	buildBatch.Env = append(os.Environ(), "CGO_ENABLED=0", "GOOS=linux", "GOARCH=amd64")
	output, err = buildBatch.CombinedOutput()
	require.NoError(t, err, string(output))
	batchOptions := func(client *dagger.Client, input replay.Source) replay.BuildOptions {
		return replay.BuildOptions{SourceDirectory: input.Directory(client), BatchCompiler: client.Host().File(batchBinary), BatchWorkers: 4}
	}
	checkBatchArtifacts := func(graph *replay.Graph) {
		root := t.TempDir()
		_, err := graph.Artifacts.Export(ctx, root)
		require.NoError(t, err)
		expected := map[string]bool{}
		for _, action := range plan.Actions {
			for _, output := range action.Outputs {
				expected[strings.TrimPrefix(output, model.TargetRoot+"/")] = true
			}
		}
		count := 0
		err = filepath.WalkDir(root, func(filename string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil || entry.IsDir() {
				return walkErr
			}
			name, err := filepath.Rel(root, filename)
			require.NoError(t, err)
			require.True(t, expected[filepath.ToSlash(name)], "unexpected compiler state or private dependency file: %s", name)
			count++
			return nil
		})
		require.NoError(t, err)
		require.Equal(t, len(expected), count)
		require.NoDirExists(t, filepath.Join(root, ".rcexp-private"))
	}
	batchGraph, err := replay.BuildAutomatic(ctx, a, plan, source, batchOptions(a, source), nil)
	require.NoError(t, err)
	batchCold, err := batchGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Len(t, batchCold.Batch, 4)
	require.Equal(t, "31 default\n", runBinary(a, batchGraph, plan.Image))
	checkBatchArtifacts(batchGraph)
	batchEditGraph, err := replay.BuildAutomatic(ctx, a, plan, appEdit, batchOptions(a, appEdit), batchGraph.History)
	require.NoError(t, err)
	batchEdited, err := batchEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, batchEditGraph.HistoryHits)
	require.Equal(t, 3, batchEdited.Reused(batchCold))
	require.Len(t, batchEdited.Batch, 1)
	require.Equal(t, "32 default\n", runBinary(a, batchEditGraph, plan.Image))
	checkBatchArtifacts(batchEditGraph)
	foreignRead := cloneRustSource(source)
	foreignFile := foreignRead["app/src/main.rs"]
	foreignFile.Contents += "\nconst _: &str = include_str!(\"../../right/Cargo.toml\");\n"
	foreignRead["app/src/main.rs"] = foreignFile
	foreignGraph, err := replay.BuildAutomatic(ctx, a, plan, foreignRead, batchOptions(a, foreignRead), batchEditGraph.History)
	require.NoError(t, err)
	_, err = foreignGraph.Artifacts.Entries(ctx)
	require.Error(t, err, "batch input visibility must not widen the supported source boundary")
	for _, op := range foreignGraph.Operations {
		if op.Action.Crate == "app" {
			_, err = op.Container.Sync(ctx)
			requireErrOut(t, err, "outside package")
		}
	}
	undeclared := cloneRustSource(source)
	undeclaredFile := undeclared["left/src/lib.rs"]
	undeclaredFile.Contents += "\nextern crate right;\n"
	undeclared["left/src/lib.rs"] = undeclaredFile
	undeclaredGraph, err := replay.BuildAutomatic(ctx, a, plan, undeclared, batchOptions(a, undeclared), batchEditGraph.History)
	require.NoError(t, err)
	_, err = undeclaredGraph.Artifacts.Entries(ctx)
	require.Error(t, err, "a compiler must not discover unrelated libraries in the batch's shared output directory")
	for _, op := range undeclaredGraph.Operations {
		if op.Action.Crate == "left" {
			_, err = op.Container.Sync(ctx)
			requireErrOut(t, err, "can't find crate for")
		}
	}
	// Five versions exceed the four-entry index. A retained version stays an
	// exact hit; the evicted version recompiles without losing other crates.
	prunedHistory := batchEditGraph.History
	var secondSource replay.Source
	var secondReport *replay.Report
	for value := 2; value <= 4; value++ {
		input := cloneRustSource(source)
		file := input["app/src/main.rs"]
		file.Contents = strings.ReplaceAll(file.Contents, "left::value() + right::value()", fmt.Sprintf("left::value() + right::value() + %d", value))
		input["app/src/main.rs"] = file
		next, err := replay.BuildAutomatic(ctx, a, plan, input, batchOptions(a, input), prunedHistory)
		require.NoError(t, err)
		report, err := next.Evaluate(ctx, 4)
		require.NoError(t, err)
		require.Equal(t, 3, next.HistoryHits)
		require.Equal(t, fmt.Sprintf("%d default\n", 31+value), runBinary(a, next, plan.Image))
		prunedHistory = next.History
		if value == 2 {
			secondSource, secondReport = input, report
		}
	}
	retainedGraph, err := replay.BuildAutomatic(ctx, a, plan, secondSource, batchOptions(a, secondSource), prunedHistory)
	require.NoError(t, err)
	retainedReport, err := retainedGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, retainedGraph.HistoryHits)
	require.Equal(t, 4, retainedReport.Reused(secondReport))
	evictedGraph, err := replay.BuildAutomatic(ctx, a, plan, source, batchOptions(a, source), prunedHistory)
	require.NoError(t, err)
	evictedReport, err := evictedGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, evictedGraph.HistoryHits)
	require.Equal(t, 3, evictedReport.Reused(batchCold))
	require.Equal(t, "31 default\n", runBinary(a, evictedGraph, plan.Image))
	var firstEditedBatch struct {
		Current string `json:"current_batch"`
	}
	firstManifest, err := batchEditGraph.History.File("manifest.json").Contents(ctx)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal([]byte(firstManifest), &firstEditedBatch))
	require.NotEmpty(t, firstEditedBatch.Current)
	retainedBatches, err := evictedGraph.History.Directory("batches").Entries(ctx)
	require.NoError(t, err)
	require.Len(t, retainedBatches, 5, "one unchanged-library batch plus four application versions")
	require.NotContains(t, retainedBatches, firstEditedBatch.Current, "the expired batch must be removed from the native snapshot")
	var ids []string
	seen := map[string]bool{}
	for _, selected := range []*replay.Graph{graph, incGraph, balancedGraph, directoryGraph} {
		for _, op := range selected.Operations {
			id, err := op.Container.ID(ctx)
			require.NoError(t, err)
			if seen[string(id)] {
				continue
			}
			seen[string(id)] = true
			ids = append(ids, string(id))
		}
	}
	// Compiler root filesystem outputs do not implicitly export every mount.
	// Export retained state and assembled artifacts as separate native roots.
	for _, output := range []*dagger.Directory{incGraph.Incremental, balancedGraph.Artifacts, directoryGraph.Artifacts} {
		id, err := output.ID(ctx)
		require.NoError(t, err)
		ids = append(ids, string(id))
	}
	historyID, err := automaticEditGraph.History.ID(ctx)
	require.NoError(t, err)
	ids = append(ids, string(historyID))
	batchHistoryID, err := batchEditGraph.History.ID(ctx)
	require.NoError(t, err)
	ids = append(ids, string(batchHistoryID))
	var exported []transferFixtureMapping
	require.NoError(t, transferFixtureSelected(ctx, a, "rust.json", ids, ids, &exported))
	_, err = outer.Container().From(alpineImage).WithMountedCache("/source", aVolume).WithMountedCache("/destination", bVolume).
		WithEnvVariable("COPY", identity.NewID()).WithExec([]string{"sh", "-ec", "mkdir -p /destination/bundles; cp /source/bundles/rust.json /destination/bundles/; cp -a /source/blobs /destination/"}).Sync(ctx)
	require.NoError(t, err)
	var imported []transferFixtureMapping
	require.NoError(t, transferFixture(ctx, b, "import", "rust.json", []string{}, &imported))
	require.NotEmpty(t, imported)
	var historyOrdinal uint64
	var decodedHistoryID call.ID
	require.NoError(t, decodedHistoryID.Decode(string(historyID)))
	var foundHistory bool
	for _, value := range exported {
		// Export mappings identify every row; only import mappings mark roots.
		if value.ResultID == decodedHistoryID.EngineResultID() {
			historyOrdinal = uint64(value.Ordinal)
			foundHistory = true
		}
	}
	require.True(t, foundHistory, "export must include the native history root")
	var importedHistory *dagger.Directory
	for _, value := range imported {
		if uint64(value.Ordinal) == historyOrdinal {
			importedHistory = dagger.Ref[*dagger.Directory](b, dagger.ID(value.Handle))
		}
	}
	require.NotNil(t, importedHistory)
	transferredHistoryDigest, err := importedHistory.Digest(ctx)
	require.NoError(t, err)
	editedHistoryDigest, err := automaticEditGraph.History.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, editedHistoryDigest, transferredHistoryDigest)
	remoteAutomaticGraph, err := replay.BuildAutomatic(ctx, b, plan, appEdit,
		replay.BuildOptions{SourceDirectory: appEdit.Directory(b)}, importedHistory)
	require.NoError(t, err)
	remoteAutomatic, err := remoteAutomaticGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, remoteAutomaticGraph.HistoryHits)
	require.Equal(t, markers(automaticEdit), markers(remoteAutomatic), "portable history must preserve all compiler results")
	remoteAutomaticEditGraph, err := replay.BuildAutomatic(ctx, b, plan, baseEdit,
		replay.BuildOptions{SourceDirectory: baseEdit.Directory(b)}, importedHistory)
	require.NoError(t, err)
	remoteAutomaticEdit, err := remoteAutomaticEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 1, remoteAutomaticEditGraph.HistoryHits)
	require.Equal(t, markers(automaticEdit)["right"], markers(remoteAutomaticEdit)["right"])
	require.Equal(t, "32 default\n", runBinary(b, remoteAutomaticEditGraph, plan.Image))
	var decodedBatchID call.ID
	require.NoError(t, decodedBatchID.Decode(string(batchHistoryID)))
	var batchOrdinal uint64
	for _, value := range exported {
		if value.ResultID == decodedBatchID.EngineResultID() {
			batchOrdinal = uint64(value.Ordinal)
		}
	}
	require.NotZero(t, batchOrdinal)
	var importedBatchHistory *dagger.Directory
	for _, value := range imported {
		if uint64(value.Ordinal) == batchOrdinal {
			importedBatchHistory = dagger.Ref[*dagger.Directory](b, dagger.ID(value.Handle))
		}
	}
	require.NotNil(t, importedBatchHistory)
	remoteBatchGraph, err := replay.BuildAutomatic(ctx, b, plan, appEdit, batchOptions(b, appEdit), importedBatchHistory)
	require.NoError(t, err)
	remoteBatch, err := remoteBatchGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, remoteBatchGraph.HistoryHits)
	require.Equal(t, markers(batchEdited), markers(remoteBatch))
	remoteBatchEditGraph, err := replay.BuildAutomatic(ctx, b, plan, baseEdit, batchOptions(b, baseEdit), importedBatchHistory)
	require.NoError(t, err)
	remoteBatchEdited, err := remoteBatchEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 1, remoteBatchEditGraph.HistoryHits)
	require.Equal(t, markers(batchEdited)["right"], markers(remoteBatchEdited)["right"])
	checkBatchArtifacts(remoteBatchEditGraph)
	require.Len(t, remoteBatchEdited.Batch, 3)
	require.Equal(t, "32 default\n", runBinary(b, remoteBatchEditGraph, plan.Image))
	remoteGraph, remote := evaluate(b, plan, source)
	require.Equal(t, 4, remote.Reused(cold), "all compiler execution markers must come from engine A")
	for i, action := range cold.Actions {
		require.Equal(t, action.Digests, remote.Actions[i].Digests, action.Crate)
	}
	require.Equal(t, "31 default\n", runBinary(b, remoteGraph, plan.Image))
	remoteBalancedGraph, err := replay.BuildWithOptions(b, plan, source, balancedOptions)
	require.NoError(t, err)
	require.NoError(t, remoteBalancedGraph.DemandFilesystem(ctx, 2))
	remoteBalanced, err := remoteBalancedGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, markers(balancedCold), markers(remoteBalanced), "balanced bundles must reuse transferred filesystem outputs")
	remoteBalancedDigest, err := remoteBalancedGraph.Artifacts.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, balancedArtifacts, remoteBalancedDigest)
	remoteDirectoryGraph, err := replay.BuildWithOptions(b, plan, source, directoryOptions)
	require.NoError(t, err)
	remoteDirectory, err := remoteDirectoryGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, markers(directoryCold), markers(remoteDirectory), "whole compiler snapshots must reuse transferred filesystem outputs")
	remoteDirectoryDigest, err := remoteDirectoryGraph.Artifacts.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, directoryArtifacts, remoteDirectoryDigest)
	remoteIncGraph, err := replay.BuildWithOptions(b, plan, source, replay.BuildOptions{IncrementalCrate: "app", ArtifactDirectories: true})
	require.NoError(t, err)
	remoteInc, err := remoteIncGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, remoteInc.Reused(incCold), "native incremental compiler outputs must transfer without exec metadata")
	remoteStateDigest, err := remoteIncGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, stateDigest, remoteStateDigest)
	remoteEditGraph, err := replay.BuildWithOptions(b, plan, appEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: remoteIncGraph.Incremental, ArtifactDirectories: true})
	require.NoError(t, err)
	remoteEdit, err := remoteEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, remoteEdit.Reused(remoteInc))
	require.Equal(t, "32 default\n", runBinary(b, remoteEditGraph, plan.Image))
	t.Logf("capture %.3fs; cold %.3fs; warm %.3fs; app edit %.3fs; dependency edit %.3fs; second engine %.3fs", plan.CaptureSeconds, cold.ReplaySeconds, warm.ReplaySeconds, appReport.ReplaySeconds, baseReport.ReplaySeconds, remote.ReplaySeconds)
}

func cloneRustSource(source replay.Source) replay.Source {
	clone := replay.Source{}
	for name, file := range source {
		clone[name] = file
	}
	return clone
}
