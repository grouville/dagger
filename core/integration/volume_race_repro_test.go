package core

import (
	"context"
	"sync"
	"time"

	"dagger.io/dagger"
	bkconfig "github.com/dagger/dagger/internal/buildkit/cmd/buildkitd/config"
	"github.com/dagger/dagger/internal/buildkit/identity"
	"github.com/dagger/dagger/internal/testutil"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

// TestEngineVolumeSubdirTOCTOURepro demonstrates the gap between engine-volume
// subdirectory validation and the runtime's later bind mount of the pathname.
func (VolumeSuite) TestEngineVolumeSubdirTOCTOURepro(ctx context.Context, t *testctx.T) {
	c := connect(ctx, t)
	engineState := c.CacheVolume("engine-volume-race-state-" + identity.NewID())
	groupData := c.CacheVolume("engine-volume-race-data-" + identity.NewID())

	_, err := c.Container().From(alpineImage).
		WithMountedCache("/data", groupData).
		WithExec([]string{"sh", "-ec", `
mkdir -p /data/models/fs/race
printf safe > /data/models/fs/race/marker
`}).
		Sync(ctx)
	require.NoError(t, err)

	const (
		engineRoot = "/engine-state"
		groupRoot  = engineRoot + "/volumes/v1/team-a"
	)
	devEngine := devEngineContainer(c,
		engineWithBkConfig(ctx, t, func(_ context.Context, _ *testctx.T, cfg bkconfig.Config) bkconfig.Config {
			cfg.Root = engineRoot
			return cfg
		}),
		func(ctr *dagger.Container) *dagger.Container {
			return ctr.
				WithMountedCache(engineRoot, engineState).
				WithMountedCache(groupRoot, groupData).
				WithNewFile("/race-target/marker", "escaped")
		},
	)
	tunneledEngine, err := c.Host().Tunnel(devEngineContainerAsService(devEngine)).Start(ctx)
	require.NoError(t, err)
	t.Cleanup(func() { _, _ = tunneledEngine.Stop(context.WithoutCancel(ctx)) })

	endpoint, err := tunneledEngine.Endpoint(ctx, dagger.ServiceEndpointOpts{Scheme: "tcp"})
	require.NoError(t, err)
	nestedClient, err := dagger.Connect(ctx,
		dagger.WithRunnerHost(endpoint),
		dagger.WithLogOutput(testutil.NewTWriter(t)),
	)
	require.NoError(t, err)
	t.Cleanup(func() { _ = nestedClient.Close() })

	rootID, err := nestedClient.EngineVolume("team-a/models").ID(ctx)
	require.NoError(t, err)
	subdirID, err := nestedClient.EngineVolume("team-a/models", dagger.EngineVolumeOpts{Subdir: "race"}).ID(ctx)
	require.NoError(t, err)

	attackCtx, stopAttack := context.WithCancel(ctx)
	t.Cleanup(stopAttack)
	go func() {
		_, _ = execWithEngineVolume(attackCtx, nestedClient, rootID, false, []string{
			"sh", "-ec", `
touch /mnt/.attacker-ready
while :; do
  mv /mnt/race /mnt/race.real 2>/dev/null || continue
  ln -s /race-target /mnt/race
  rm /mnt/race
  mv /mnt/race.real /mnt/race
done
`,
		})
	}()
	waitForEngineVolumeFile(ctx, t, nestedClient, rootID, "/mnt/.attacker-ready")

	const attempts = 64
	results := make(chan string, attempts)
	var wg sync.WaitGroup
	for range attempts {
		wg.Add(1)
		go func() {
			defer wg.Done()
			attemptCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
			defer cancel()
			out, err := execWithEngineVolume(attemptCtx, nestedClient, subdirID, false, []string{
				"sh", "-ec", "cat /mnt/marker",
			})
			if err == nil {
				results <- out
			}
		}()
	}
	wg.Wait()
	close(results)
	stopAttack()

	safeMounts := 0
	for out := range results {
		if out == "escaped" {
			t.Fatal("engine-volume subdirectory escaped to an engine-host path")
		}
		if out == "safe" {
			safeMounts++
		}
	}
	require.Positive(t, safeMounts, "expected at least one successful contained mount")
}
