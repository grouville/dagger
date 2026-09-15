package drivers

import (
	"context"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"testing"

	"github.com/adrg/xdg"
	"github.com/stretchr/testify/require"
)

func TestImageDriverCreateSharesEngineSocket(t *testing.T) {
	t.Parallel()

	backend := &captureContainerBackend{}
	driver := &imageDriver{backend: backend}
	socketDir := t.TempDir()

	_, err := driver.create(t.Context(), containerCreateOpts{
		imageRef:  "registry.example.com/dagger-engine:v0.21.0",
		socketDir: socketDir,
	}, &DriverOpts{})
	require.NoError(t, err)

	require.Contains(t, backend.runOpts.volumes, socketDir+":"+engineSocketDirInContainer)
	require.Equal(t, []string{
		"--debug",
		"--debugaddr",
		defaultDebugListenerAddress,
		"--group",
		strconv.Itoa(os.Getgid()),
	}, backend.runOpts.args)
}

type dialCountBackend struct {
	captureContainerBackend
	dials int
}

func (b *dialCountBackend) ContainerDial(context.Context, string, []string) (net.Conn, error) {
	b.dials++
	c, _ := net.Pipe()
	return c, nil
}

func TestContainerConnectorPrefersEngineSocket(t *testing.T) {
	t.Parallel()

	socketDir := t.TempDir()
	backend := &dialCountBackend{}
	connector := containerConnector{backend: backend, host: "engine", socketDir: socketDir}

	// No socket shared yet: the exec tunnel is used.
	conn, err := connector.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 1, backend.dials)

	// Once the engine's socket appears it is dialed directly.
	l, err := net.Listen("unix", filepath.Join(socketDir, "engine.sock"))
	require.NoError(t, err)
	defer l.Close()
	go func() {
		c, err := l.Accept()
		if err == nil {
			c.Close()
		}
	}()
	conn, err = connector.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 1, backend.dials)
}

type discoveryCountBackend struct {
	captureContainerBackend
	lists, starts int
}

func (b *discoveryCountBackend) ContainerLs(context.Context) ([]string, error) {
	b.lists++
	return nil, nil
}

func (b *discoveryCountBackend) ContainerStart(context.Context, string) error {
	b.starts++
	return nil
}

func TestImageDriverSkipsDiscoveryWhenEngineSocketAnswers(t *testing.T) {
	// Unix socket paths are limited to ~108 bytes; t.TempDir is too long.
	runtimeDir, err := os.MkdirTemp("", "dagger-rt")
	require.NoError(t, err)
	t.Cleanup(func() { os.RemoveAll(runtimeDir) })
	t.Setenv("XDG_RUNTIME_DIR", runtimeDir)
	xdg.Reload()
	if runtime.GOOS != "linux" {
		t.Skip("engine sockets are only shared on linux")
	}

	backend := &discoveryCountBackend{}
	driver := &imageDriver{backend: backend}
	target := &url.URL{Scheme: "image", Host: "registry.example.com", Path: "/dagger-engine:v0.21.0"}

	// No engine yet: discovery runs and the container is created.
	_, err = driver.Provision(t.Context(), target, &DriverOpts{})
	require.NoError(t, err)
	require.Equal(t, 1, backend.lists)
	require.Equal(t, "dagger-engine-v0.21.0", backend.runName)

	// The engine now answers on its socket: nothing is asked of the runtime.
	dir, ok := engineSocketDir("dagger-engine-v0.21.0")
	require.True(t, ok)
	l, err := net.Listen("unix", filepath.Join(dir, "engine.sock"))
	require.NoError(t, err)
	defer l.Close()
	go func() {
		for {
			c, err := l.Accept()
			if err != nil {
				return
			}
			c.Close()
		}
	}()
	available, err := driver.Available(t.Context(), target)
	require.NoError(t, err)
	require.True(t, available)
	connector, err := driver.Provision(t.Context(), target, &DriverOpts{})
	require.NoError(t, err)
	require.Equal(t, 1, backend.lists)
	require.Equal(t, 0, backend.starts)
	require.Equal(t, dir, connector.(containerConnector).socketDir)
}
