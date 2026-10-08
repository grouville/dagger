package core

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"

	"dagger.io/dagger"
	"dagger.io/dagger/engineconn"
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
	// Preserve rustc's within-crate state as a native Directory. Seeding an
	// edited build must leave the old snapshot immutable and unrelated crate
	// results reusable. The experiment only enables incremental for the app.
	incGraph, err := replay.BuildWithOptions(a, plan, source, replay.BuildOptions{IncrementalCrate: "app"})
	require.NoError(t, err)
	incCold, err := incGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	stateEntries, err := incGraph.Incremental.Entries(ctx)
	require.NoError(t, err)
	require.NotEmpty(t, stateEntries)
	stateDigest, err := incGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	incEditGraph, err := replay.BuildWithOptions(a, plan, appEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: incGraph.Incremental})
	require.NoError(t, err)
	incEdit, err := incEditGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 3, incEdit.Reused(incCold))
	require.Equal(t, "32 default\n", runBinary(a, incEditGraph, plan.Image))
	incDepGraph, err := replay.BuildWithOptions(a, plan, baseEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: incGraph.Incremental})
	require.NoError(t, err)
	incDep, err := incDepGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 1, incDep.Reused(incCold), "only the unrelated right crate remains reusable")
	require.Equal(t, "32 default\n", runBinary(a, incDepGraph, plan.Image))
	afterSeedDigest, err := incGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, stateDigest, afterSeedDigest, "seed snapshot must remain immutable")
	var ids []string
	seen := map[string]bool{}
	for _, op := range append(append([]replay.Operation{}, graph.Operations...), incGraph.Operations...) {
		id, err := op.Container.ID(ctx)
		require.NoError(t, err)
		if seen[string(id)] {
			continue
		}
		seen[string(id)] = true
		ids = append(ids, string(id))
	}
	// Compiler root filesystem outputs do not implicitly export every mount.
	// Treat retained incremental state as a separate native cache output root.
	stateID, err := incGraph.Incremental.ID(ctx)
	require.NoError(t, err)
	ids = append(ids, string(stateID))
	var exported []transferFixtureMapping
	require.NoError(t, transferFixtureSelected(ctx, a, "rust.json", ids, ids, &exported))
	_, err = outer.Container().From(alpineImage).WithMountedCache("/source", aVolume).WithMountedCache("/destination", bVolume).
		WithEnvVariable("COPY", identity.NewID()).WithExec([]string{"sh", "-ec", "mkdir -p /destination/bundles; cp /source/bundles/rust.json /destination/bundles/; cp -a /source/blobs /destination/"}).Sync(ctx)
	require.NoError(t, err)
	var imported []transferFixtureMapping
	require.NoError(t, transferFixture(ctx, b, "import", "rust.json", []string{}, &imported))
	require.NotEmpty(t, imported)
	remoteGraph, remote := evaluate(b, plan, source)
	require.Equal(t, 4, remote.Reused(cold), "all compiler execution markers must come from engine A")
	for i, action := range cold.Actions {
		require.Equal(t, action.Digests, remote.Actions[i].Digests, action.Crate)
	}
	require.Equal(t, "31 default\n", runBinary(b, remoteGraph, plan.Image))
	remoteIncGraph, err := replay.BuildWithOptions(b, plan, source, replay.BuildOptions{IncrementalCrate: "app"})
	require.NoError(t, err)
	remoteInc, err := remoteIncGraph.Evaluate(ctx, 4)
	require.NoError(t, err)
	require.Equal(t, 4, remoteInc.Reused(incCold), "native incremental compiler outputs must transfer without exec metadata")
	remoteStateDigest, err := remoteIncGraph.Incremental.Digest(ctx)
	require.NoError(t, err)
	require.Equal(t, stateDigest, remoteStateDigest)
	remoteEditGraph, err := replay.BuildWithOptions(b, plan, appEdit, replay.BuildOptions{IncrementalCrate: "app", IncrementalSeed: remoteIncGraph.Incremental})
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
