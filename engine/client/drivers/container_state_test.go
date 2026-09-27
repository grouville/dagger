package drivers

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type stateEngineBackend struct {
	existingEngineBackend
	state    containerState
	stateErr error
	startErr error
	runErr   error
}

func (b *stateEngineBackend) ContainerState(_ context.Context, name string) (containerState, error) {
	b.record("state " + name)
	return b.state, b.stateErr
}
func (b *stateEngineBackend) ContainerStart(_ context.Context, name string) error {
	b.record("start " + name)
	return b.startErr
}
func (b *stateEngineBackend) ContainerRun(ctx context.Context, name string, opts runOpts) error {
	b.record("run " + name)
	if b.runErr != nil {
		return b.runErr
	}
	return b.captureContainerBackend.ContainerRun(ctx, name, opts)
}

func TestImageDriverSkipsStartForRunningContainer(t *testing.T) {
	backend := &stateEngineBackend{state: containerState{exists: true, running: true}}
	backend.containers = []string{"dagger-engine-v0.20.0", "dagger-engine-v0.21.0", "unrelated"}
	target, err := (&imageDriver{backend: backend}).create(t.Context(), containerCreateOpts{imageRef: "registry.example.com/dagger-engine:v0.21.0", cleanup: true}, &DriverOpts{})
	require.NoError(t, err)
	require.Equal(t, "dagger-engine-v0.21.0", target.Host)
	require.Equal(t, []string{"state dagger-engine-v0.21.0"}, backend.callsBefore("ls"))
	require.Eventually(t, func() bool { return slices.Contains(backend.calls(), "remove dagger-engine-v0.20.0") }, 5*time.Second, 10*time.Millisecond)
	require.NotContains(t, backend.calls(), "start dagger-engine-v0.21.0")
	require.NotContains(t, backend.calls(), "remove dagger-engine-v0.21.0")
	require.NotContains(t, backend.calls(), "remove unrelated")
	require.Empty(t, backend.runName)
}

func TestImageDriverStateFallbacks(t *testing.T) {
	name := "dagger-engine-v0.21.0"
	for _, tc := range []struct {
		name                       string
		state                      containerState
		stateErr, startErr, runErr error
		listed                     bool
		wantError                  error
		wantCalls                  []string
	}{
		{name: "stopped", state: containerState{exists: true}, wantCalls: []string{"state " + name, "start " + name}},
		{name: "missing", wantCalls: []string{"state " + name, "ls", "run " + name}},
		{name: "lookup error still finds existing", stateErr: errors.New("inspect failed"), listed: true, wantCalls: []string{"state " + name, "ls", "start " + name}},
		{name: "canceled lookup", stateErr: context.Canceled, wantError: context.Canceled, wantCalls: []string{"state " + name}},
		{name: "start error", state: containerState{exists: true}, startErr: context.DeadlineExceeded, wantError: context.DeadlineExceeded, wantCalls: []string{"state " + name, "start " + name}},
		{name: "creation race", runErr: errContainerAlreadyExists, wantCalls: []string{"state " + name, "ls", "run " + name}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			backend := &stateEngineBackend{state: tc.state, stateErr: tc.stateErr, startErr: tc.startErr, runErr: tc.runErr}
			if tc.listed {
				backend.containers = []string{name}
			}
			target, err := (&imageDriver{backend: backend}).create(t.Context(), containerCreateOpts{imageRef: "registry.example.com/dagger-engine:v0.21.0"}, &DriverOpts{})
			if tc.wantError != nil {
				require.ErrorIs(t, err, tc.wantError)
				require.Nil(t, target)
			} else {
				require.NoError(t, err)
				require.Equal(t, name, target.Host)
			}
			require.Equal(t, tc.wantCalls, backend.calls())
		})
	}
}

func TestContainerStateLegacyBackend(t *testing.T) {
	backend := &existingEngineBackend{containers: []string{"fixture"}}
	state, err := lookupContainerState(t.Context(), backend, "fixture")
	require.NoError(t, err)
	require.True(t, state.exists)
	require.False(t, state.running)
	require.Equal(t, []string{"exists fixture"}, backend.calls())
}

func TestContainerRunningProtocol(t *testing.T) {
	for _, tc := range []struct {
		input   string
		running bool
	}{
		{"running", true}, {"running\n", true}, {" \trunning\r\n", true},
		{"paused", false}, {"restarting", false}, {"created", false}, {"exited", false}, {"dead", false}, {"removing", false}, {"true", false}, {"false", false}, {"", false}, {"<no value>", false}, {"null", false}, {"True", false}, {"\"true\"", false}, {"true false", false}, {"true\nfalse", false}, {"{}", false},
	} {
		t.Run(tc.input, func(t *testing.T) { require.Equal(t, tc.running, containerIsRunning(tc.input)) })
	}
}

func TestDockerContainerStateCommand(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("fake POSIX CLI protocol fixture")
	}
	dir := t.TempDir()
	log := filepath.Join(dir, "calls")
	script := `#!/bin/sh
if [ "$#" != 5 ] || [ "$1" != container ] || [ "$2" != inspect ] || [ "$3" != fixture ] || [ "$4" != --format ] || [ "$5" != "$DAGGER_TEST_STATE_FORMAT" ]; then
 printf 'unexpected argument protocol\n' >&2
 exit 64
fi
printf '%s\n' "$5" >> "$DAGGER_TEST_STATE_LOG"
printf '%s' "$DAGGER_TEST_STATE_REPLY"
printf '%s' "$DAGGER_TEST_STATE_STDERR" >&2
exit "$DAGGER_TEST_STATE_EXIT"
`
	for _, name := range []string{"docker", "podman", "nerdctl"} {
		require.NoError(t, os.WriteFile(filepath.Join(dir, name), []byte(script), 0o700))
	}
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("DAGGER_TEST_STATE_LOG", log)
	for _, tc := range []struct {
		name, cmd, format, reply, stderr, status string
		exists, running, wantErr                 bool
	}{
		{"running", "docker", "{{.State.Status}}", "running\n", "", "0", true, true, false},
		{"stopped", "docker", "{{.State.Status}}", "exited\n", "", "0", true, false, false},
		{"paused", "docker", "{{.State.Status}}", "paused", "", "0", true, false, false},
		{"restarting", "docker", "{{.State.Status}}", "restarting", "", "0", true, false, false},
		{"unknown successful output", "docker", "{{.State.Status}}", "<no value>", "", "0", true, false, false},
		{"missing", "docker", "{{.State.Status}}", "", "Error: No such container: fixture", "1", false, false, false},
		{"denied", "docker", "{{.State.Status}}", "", "permission denied", "1", false, false, true},
		{"podman legacy", "podman", "{{ .ID }}", "fake-container-id", "", "0", true, false, false},
		{"nerdctl legacy", "nerdctl", "{{ .ID }}", "fake-container-id", "", "0", true, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			require.NoError(t, os.WriteFile(log, nil, 0o600))
			t.Setenv("DAGGER_TEST_STATE_FORMAT", tc.format)
			t.Setenv("DAGGER_TEST_STATE_REPLY", tc.reply)
			t.Setenv("DAGGER_TEST_STATE_STDERR", tc.stderr)
			t.Setenv("DAGGER_TEST_STATE_EXIT", tc.status)
			state, err := (docker{cmd: tc.cmd}).ContainerState(t.Context(), "fixture")
			require.Equal(t, tc.exists, state.exists)
			require.Equal(t, tc.running, state.running)
			if tc.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
			}
			output, readErr := os.ReadFile(log)
			require.NoError(t, readErr)
			require.Equal(t, tc.format, strings.TrimSpace(string(output)), "one existing inspect, without extra process probes")
		})
	}
}
