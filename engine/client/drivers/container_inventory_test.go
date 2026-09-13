package drivers

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestContainerInventoryPrefilterCommands(t *testing.T) {
	for _, command := range []string{"docker", "podman", "nerdctl", "finch", "container"} {
		t.Run(command, func(t *testing.T) {
			dir := runtimeTestPath(t)
			argsFile := filepath.Join(dir, "args")
			t.Setenv("DAGGER_TEST_ARGS", argsFile)
			inventory := "unrelated\ndagger-engine-old\ncustom.v1\ncustomXv1\nxdagger-engine-old\ncustom.v1-extra"
			var backend containerBackend = docker{cmd: command}
			wantArgs := []string{"ps", "-a", "--format", "{{.Names}}"}
			if command == "docker" {
				wantArgs = append(wantArgs, "--filter", `name=^/?(dagger-engine-.*|custom\.v1)$`)
			}
			if command == "container" {
				backend = apple{}
				wantArgs = []string{"ls", "-a", "--format", "json"}
				inventory = `[{"configuration":{"id":"unrelated"}},{"configuration":{"id":"dagger-engine-old"}},{"configuration":{"id":"custom.v1"}},{"configuration":{"id":"customXv1"}}]`
			}
			t.Setenv("DAGGER_TEST_INVENTORY", inventory)
			writeRuntimeCommand(t, dir, command, `printf '%s\n' "$@" > "$DAGGER_TEST_ARGS"
printf '%s\n' "$DAGGER_TEST_INVENTORY"`)
			driver := &imageDriver{backend: backend}
			names, err := driver.collectLeftoverEngines(t.Context(), "custom.v1")
			require.NoError(t, err)
			// A server-side prefilter can include aliases or overmatch. The
			// common predicate must still reject unrelated canonical names.
			require.Equal(t, []string{"dagger-engine-old", "custom.v1"}, names)
			args, err := os.ReadFile(argsFile)
			require.NoError(t, err)
			require.Equal(t, wantArgs, strings.Split(strings.TrimSuffix(string(args), "\n"), "\n"))
			if command == "docker" {
				filter := regexp.MustCompile(strings.TrimPrefix(wantArgs[len(wantArgs)-1], "name="))
				for _, name := range []string{"dagger-engine-old", "dagger-engine-", "custom.v1"} {
					require.Regexp(t, filter, name)
					require.Regexp(t, filter, "/"+name)
				}
				for _, name := range []string{"xdagger-engine-old", "customXv1", "custom.v1-extra", ""} {
					require.NotRegexp(t, filter, name)
				}
			}
		})
	}
}

func TestContainerInventoryNoHints(t *testing.T) {
	dir := runtimeTestPath(t)
	writeRuntimeCommand(t, dir, "docker", `test "$#" = 4 || exit 2
printf '%s\n' unrelated dagger-engine-old`)
	names, err := (docker{cmd: "docker"}).ContainerLs(t.Context(), listOpts{})
	require.NoError(t, err)
	require.Equal(t, []string{"unrelated", "dagger-engine-old"}, names)
}

func TestContainerInventorySelectionAndCleanup(t *testing.T) {
	for _, target := range []string{"dagger-engine-target", "custom.v1"} {
		for _, cleanup := range []bool{false, true} {
			t.Run(target+"/cleanup="+map[bool]string{false: "false", true: "true"}[cleanup], func(t *testing.T) {
				backend := &inventoryBackend{names: []string{
					"unrelated", "dagger-engine-old", target, "customXv1", "custom.v1-extra",
				}}
				driver := &imageDriver{backend: backend}
				got, err := driver.create(t.Context(), containerCreateOpts{
					imageRef: "registry.example.com/dagger-engine:test", containerName: target, cleanup: cleanup,
				}, &DriverOpts{})
				require.NoError(t, err)
				require.Equal(t, target, got.Host)
				require.Equal(t, []string{target}, backend.started, "existing stopped targets still need start")
				require.Empty(t, backend.runName, "do not recreate an existing custom target")
				require.Equal(t, listOpts{namePrefix: containerNamePrefix, names: []string{target}}, backend.opts)
				if cleanup {
					require.Equal(t, []string{"dagger-engine-old"}, backend.removed)
				} else {
					require.Empty(t, backend.removed)
				}
			})
		}
	}
}

func TestContainerInventoryPreserveVersions(t *testing.T) {
	backend := &inventoryBackend{names: []string{"unrelated", "dagger-engine-current", "dagger-engine-old", "custom.v1"}}
	driver := &imageDriver{backend: backend}
	names, err := driver.collectLeftoverEngines(t.Context())
	require.NoError(t, err)
	require.Equal(t, listOpts{namePrefix: containerNamePrefix}, backend.opts)
	driver.garbageCollectEngines(t.Context(), true, engineNames([]string{"current", ""}), names)
	require.Equal(t, []string{"dagger-engine-old"}, backend.removed)
}

func TestContainerInventoryEmptyAndErrors(t *testing.T) {
	backend := &inventoryBackend{}
	driver := &imageDriver{backend: backend}
	names, err := driver.collectLeftoverEngines(t.Context(), "custom.v1")
	require.NoError(t, err)
	require.Empty(t, names)
	backend.listErr = errors.New("runtime unavailable")
	_, err = driver.collectLeftoverEngines(t.Context())
	require.ErrorIs(t, err, backend.listErr)

	// Preserve the existing cancellation path before start/run/cleanup.
	backend.listErr = context.Canceled
	_, err = driver.create(t.Context(), containerCreateOpts{
		imageRef: "registry.example.com/dagger-engine:test", containerName: "custom.v1", cleanup: true,
	}, &DriverOpts{})
	require.ErrorIs(t, err, context.Canceled)
	require.Empty(t, backend.started)
	require.Empty(t, backend.runName)
	require.Empty(t, backend.removed)
}

type inventoryBackend struct {
	captureContainerBackend
	names   []string
	opts    listOpts
	listErr error
	started []string
	removed []string
}

func (b *inventoryBackend) ContainerLs(_ context.Context, opts listOpts) ([]string, error) {
	b.opts = opts
	return slices.Clone(b.names), b.listErr
}

func (b *inventoryBackend) ContainerStart(_ context.Context, name string) error {
	b.started = append(b.started, name)
	return nil
}

func (b *inventoryBackend) ContainerRemove(_ context.Context, name string) error {
	b.removed = append(b.removed, name)
	return nil
}
