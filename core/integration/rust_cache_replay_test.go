package core

import (
	"context"
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
	var ids []string
	for _, op := range graph.Operations {
		id, err := op.Container.ID(ctx)
		require.NoError(t, err)
		ids = append(ids, string(id))
	}
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
	t.Logf("capture %.3fs; cold %.3fs; warm %.3fs; app edit %.3fs; dependency edit %.3fs; second engine %.3fs", plan.CaptureSeconds, cold.ReplaySeconds, warm.ReplaySeconds, appReport.ReplaySeconds, baseReport.ReplaySeconds, remote.ReplaySeconds)
}

func cloneRustSource(source replay.Source) replay.Source {
	clone := replay.Source{}
	for name, file := range source {
		clone[name] = file
	}
	return clone
}
