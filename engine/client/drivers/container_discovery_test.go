package drivers

import (
	"context"
	"errors"
	"regexp"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCollectEngines(t *testing.T) {
	for _, tc := range []struct {
		name       string
		includeOld bool
		additional []string
		patterns   []string
		want       []string
	}{
		{
			name: "managed target and old engines", includeOld: true,
			additional: []string{"dagger-engine-current", "dagger-engine-current"},
			patterns:   []string{"^/?dagger-engine-"},
			want:       []string{"dagger-engine-current", "dagger-engine-old"},
		},
		{
			name: "custom target and old engines", includeOld: true,
			additional: []string{"custom.v1", "custom.v1"},
			patterns:   []string{"^/?dagger-engine-", `^/?custom\.v1$`},
			want:       []string{"dagger-engine-current", "dagger-engine-old", "custom.v1"},
		},
		{
			name: "managed target only", additional: []string{"dagger-engine-current"},
			patterns: []string{"^/?dagger-engine-current$"},
			want:     []string{"dagger-engine-current"},
		},
		{
			name: "custom target only", additional: []string{"custom.v1", "custom.v1"},
			patterns: []string{`^/?custom\.v1$`},
			want:     []string{"custom.v1"},
		},
		{
			name: "old engines only", includeOld: true,
			patterns: []string{"^/?dagger-engine-"},
			want:     []string{"dagger-engine-current", "dagger-engine-old"},
		},
		{
			name: "all regex metacharacters are literal", additional: []string{"custom.[v1]+$"},
			patterns: []string{`^/?custom\.\[v1\]\+\$$`},
			want:     []string{"custom.[v1]+$"},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			// Ignore hints like the Apple backend, including false-positive names
			// that must never cross the local start/remove boundary.
			backend := &discoveryBackend{names: []string{
				"dagger-engine-current", "dagger-engine-old", "custom.v1", "custom.[v1]+$",
				"customXv1", "custom.v1-extra", "unrelated-dagger-engine-old", "unrelated",
				"/dagger-engine-old", "Dagger-engine-old", "",
			}}
			driver := &imageDriver{backend: backend}
			names, err := driver.collectEngines(t.Context(), tc.includeOld, tc.additional...)
			require.NoError(t, err)
			require.Equal(t, tc.want, names)
			require.Equal(t, tc.patterns, backend.patterns)
			for _, name := range tc.want {
				for _, candidate := range []string{name, "/" + name} {
					matched := false
					for _, pattern := range backend.patterns {
						matched = matched || regexp.MustCompile(pattern).MatchString(candidate)
					}
					require.True(t, matched, "filter hints must include %q", candidate)
				}
			}
		})
	}
}

func TestDockerContainerLs(t *testing.T) {
	for _, command := range []string{"docker", "podman", "nerdctl", "finch"} {
		t.Run(command, func(t *testing.T) {
			dir := runtimeTestPath(t)
			writeRuntimeCommand(t, dir, command, `
test "$#" -eq 8 || exit 2
test "$1" = ps && test "$2" = -a && test "$3" = --format && test "$4" = '{{.Names}}' || exit 2
test "$5" = --filter && test "$6" = 'name=^/?dagger-engine-' || exit 2
test "$7" = --filter && test "$8" = 'name=^/?custom\.v1$' || exit 2
printf '%s\n' dagger-engine-current custom.v1
`)
			names, err := (docker{cmd: command}).ContainerLs(t.Context(), "^/?dagger-engine-", `^/?custom\.v1$`)
			require.NoError(t, err)
			require.Equal(t, []string{"dagger-engine-current", "custom.v1"}, names)
		})
	}
	t.Run("no hints keeps original command", func(t *testing.T) {
		dir := runtimeTestPath(t)
		writeRuntimeCommand(t, dir, "docker", `test "$#" -eq 4 && test "$*" = 'ps -a --format {{.Names}}'`)
		names, err := (docker{cmd: "docker"}).ContainerLs(t.Context())
		require.NoError(t, err)
		require.Empty(t, names)
	})
}

func TestAppleContainerLs(t *testing.T) {
	dir := runtimeTestPath(t)
	writeRuntimeCommand(t, dir, "container", `
test "$#" -eq 4 && test "$*" = 'ls -a --format json' || exit 2
printf '%s\n' '[{"configuration":{"id":"dagger-engine-current"}},{"configuration":{"id":"unrelated"}}]'
`)
	names, err := (apple{}).ContainerLs(t.Context(), "^/?dagger-engine-")
	require.NoError(t, err)
	require.Equal(t, []string{"dagger-engine-current", "unrelated"}, names)
}

func TestContainerLsFailure(t *testing.T) {
	for _, tc := range []struct {
		command string
		backend containerBackend
	}{
		{"docker", docker{cmd: "docker"}},
		{"container", apple{}},
	} {
		t.Run(tc.command, func(t *testing.T) {
			dir := runtimeTestPath(t)
			writeRuntimeCommand(t, dir, tc.command, "exit 7")
			names, err := tc.backend.ContainerLs(t.Context(), "^/?dagger-engine-")
			require.Nil(t, names)
			require.ErrorContains(t, err, "exit status 7")
			ctx, cancel := context.WithCancel(t.Context())
			cancel()
			names, err = tc.backend.ContainerLs(ctx, "^/?dagger-engine-")
			require.Nil(t, names)
			require.ErrorIs(t, err, context.Canceled)
		})
	}
}

func TestImageDriverCreateDiscovery(t *testing.T) {
	for _, tc := range []struct {
		name    string
		target  string
		cleanup bool
		exists  bool
	}{
		{"reuse managed with cleanup", "dagger-engine-current", true, true},
		{"reuse managed without cleanup", "dagger-engine-current", false, true},
		{"reuse custom with cleanup", "custom.v1", true, true},
		{"reuse custom without cleanup", "custom.v1", false, true},
		{"create with cleanup", "custom.v1", true, false},
		{"create without cleanup", "custom.v1", false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			backend := &discoveryBackend{names: []string{"unrelated", "dagger-engine-old", "customXv1"}}
			if tc.exists {
				backend.names = append(backend.names, tc.target)
			}
			driver := &imageDriver{backend: backend}
			target, err := driver.create(t.Context(), containerCreateOpts{
				imageRef: "registry.example.com/dagger-engine:current", containerName: tc.target, cleanup: tc.cleanup,
			}, &DriverOpts{})
			require.NoError(t, err)
			require.Equal(t, tc.target, target.Host)
			if tc.exists {
				require.Equal(t, []string{tc.target}, backend.started)
				require.Empty(t, backend.runName)
			} else {
				require.Empty(t, backend.started)
				require.Equal(t, tc.target, backend.runName)
			}
			if tc.cleanup {
				require.Equal(t, []string{"dagger-engine-old"}, backend.removed)
			} else {
				require.Empty(t, backend.removed)
			}
		})
	}
	t.Run("list failure retains create fallback", func(t *testing.T) {
		backend := &discoveryBackend{listErr: errors.New("listing failed")}
		driver := &imageDriver{backend: backend}
		_, err := driver.create(t.Context(), containerCreateOpts{imageRef: "registry.example.com/engine:current", cleanup: true}, &DriverOpts{})
		require.NoError(t, err)
		require.Equal(t, "dagger-engine-current", backend.runName)
		require.Empty(t, backend.removed)
	})
	t.Run("canceled listing does not create", func(t *testing.T) {
		backend := &discoveryBackend{listErr: context.Canceled}
		driver := &imageDriver{backend: backend}
		_, err := driver.create(t.Context(), containerCreateOpts{imageRef: "registry.example.com/engine:current"}, &DriverOpts{})
		require.ErrorIs(t, err, context.Canceled)
		require.Empty(t, backend.runName)
		require.Empty(t, backend.removed)
	})
}

func TestGarbageCollectEnginePreservesNames(t *testing.T) {
	backend := &discoveryBackend{}
	driver := &imageDriver{backend: backend}
	driver.garbageCollectEngines(t.Context(), true, engineNames([]string{"current", ""}), []string{"", "dagger-engine-current", "dagger-engine-old"})
	require.Equal(t, []string{"dagger-engine-old"}, backend.removed)
}

type discoveryBackend struct {
	captureContainerBackend
	names    []string
	patterns []string
	listErr  error
	started  []string
	removed  []string
}

func (b *discoveryBackend) ContainerLs(_ context.Context, patterns ...string) ([]string, error) {
	b.patterns = patterns
	return b.names, b.listErr
}

func (b *discoveryBackend) ContainerStart(_ context.Context, name string) error {
	b.started = append(b.started, name)
	return nil
}

func (b *discoveryBackend) ContainerRemove(_ context.Context, name string) error {
	b.removed = append(b.removed, name)
	return nil
}
