package drivers

import (
	"context"
	"crypto/rand"
	"os"
	"os/exec"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// This opt-in contract test never pulls/removes images or removes existing
// containers. It owns only the stopped containers created below and validates
// each immutable ID, name, image and ownership label before cleanup.
func TestDockerContainerInventoryContract(t *testing.T) {
	if os.Getenv("DAGGER_TEST_DOCKER_INVENTORY") != "1" {
		t.Skip("set DAGGER_TEST_DOCKER_INVENTORY=1 and provide an already installed image")
	}
	image := os.Getenv("DAGGER_TEST_INVENTORY_IMAGE")
	require.NotEmpty(t, image)
	ctx, cancel := context.WithTimeout(t.Context(), 60*time.Second)
	defer cancel()
	imageID, err := exec.CommandContext(ctx, "docker", "image", "inspect", image, "--format", "{{.Id}}").Output()
	require.NoError(t, err)
	owner := strings.ToLower(rand.Text())
	label := "dagger.inventory.contract"
	custom := "inventory-" + owner + ".v1"
	names := []string{containerNamePrefix + "inventory-" + owner, custom, "inventory-" + owner + "Xv1", custom + "-extra"}
	for _, name := range names {
		out, err := exec.CommandContext(ctx, "docker", "create", "--pull=never", "--name", name,
			"--label", label+"="+owner, image, "/bin/true").Output()
		require.NoError(t, err)
		id := strings.TrimSpace(string(out))
		require.Regexp(t, "^[a-f0-9]{64}$", id)
		t.Cleanup(func() {
			cleanupCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			format := `{{.Id}} {{.Name}} {{.Image}} {{index .Config.Labels "dagger.inventory.contract"}} {{.State.Status}}`
			got, err := exec.CommandContext(cleanupCtx, "docker", "inspect", id, "--format", format).Output()
			if !assertInventoryCleanupIdentity(t, err, string(got), id+" /"+name+" "+strings.TrimSpace(string(imageID))+" "+owner+" created\n") {
				return
			}
			output, err := exec.CommandContext(cleanupCtx, "docker", "rm", id).CombinedOutput()
			require.NoError(t, err, "remove owned container %s: %s", id, output)
		})
	}
	backend := docker{cmd: "docker"}
	all, err := backend.ContainerLs(ctx, listOpts{})
	require.NoError(t, err)
	for _, name := range names {
		require.Contains(t, all, name, "stopped containers remain visible")
	}
	for _, exact := range [][]string{nil, {custom}, {custom, names[2]}, {custom + "-missing"}} {
		got, err := backend.ContainerLs(ctx, listOpts{namePrefix: containerNamePrefix, names: exact})
		require.NoError(t, err)
		want := slices.DeleteFunc(slices.Clone(all), func(name string) bool {
			return !strings.HasPrefix(name, containerNamePrefix) && !slices.Contains(exact, name)
		})
		require.Equal(t, want, got, "preserve old predicate and ordering")
	}
	// Fail instead of crediting a changed inventory as filter behavior.
	after, err := backend.ContainerLs(ctx, listOpts{})
	require.NoError(t, err)
	require.Equal(t, all, after)
}

func assertInventoryCleanupIdentity(t *testing.T, err error, got, want string) bool {
	t.Helper()
	if err != nil || got != want {
		t.Errorf("retain owned test container after failed cleanup identity check: err=%v, got=%q, want=%q", err, got, want)
		return false
	}
	return true
}
