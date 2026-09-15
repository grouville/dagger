package drivers

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"testing"

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
