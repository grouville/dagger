package drivers

import (
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/adrg/xdg"
	"github.com/stretchr/testify/require"

	"github.com/dagger/dagger/engine"
)

// endpointTestEnv gives the driver a private runtime dir and a local daemon.
func endpointTestEnv(t *testing.T) {
	t.Helper()
	dir, err := os.MkdirTemp("", "dagger-rt")
	require.NoError(t, err)
	t.Cleanup(func() { os.RemoveAll(dir) })
	t.Setenv("XDG_RUNTIME_DIR", dir)
	t.Setenv("DOCKER_HOST", "")
	xdg.Reload()
}

func TestImageDriverCreatePublishesLocalEndpoint(t *testing.T) {
	endpointTestEnv(t)
	backend := &captureContainerBackend{}
	driver := &imageDriver{backend: backend}
	target := &url.URL{Scheme: "image", Host: "registry.example.com", Path: "/dagger-engine:v0.21.0"}

	connector, err := driver.Provision(t.Context(), target, &DriverOpts{})
	require.NoError(t, err)
	require.Equal(t, "dagger-engine-v0.21.0", backend.runName)

	dir, ok := localEndpointDir("dagger-engine-v0.21.0")
	require.True(t, ok)
	ep, ok := loadLocalEndpoint(dir)
	require.True(t, ok)
	require.Len(t, ep.token, 64)
	_, port, err := net.SplitHostPort(ep.addr)
	require.NoError(t, err)

	// The token file is private and mounted read-only; the port is loopback only.
	info, err := os.Stat(filepath.Join(dir, endpointTokenFile))
	require.NoError(t, err)
	require.Equal(t, os.FileMode(0o600), info.Mode().Perm())
	require.Contains(t, backend.runOpts.volumes, filepath.Join(dir, endpointTokenFile)+":"+endpointTokenInPath+":ro")
	require.Contains(t, backend.runOpts.ports, "127.0.0.1:"+port+":"+port)
	require.Equal(t, []string{
		"--debug", "--debugaddr", defaultDebugListenerAddress,
		"--addr", "tcp://0.0.0.0:" + port, "--token-file", endpointTokenInPath,
	}, backend.runOpts.args)
	require.Equal(t, ep, connector.(containerConnector).endpoint)
}

func TestContainerConnectorPrefersLocalEndpoint(t *testing.T) {
	endpointTestEnv(t)
	dir, ok := localEndpointDir("dagger-engine-ep")
	require.True(t, ok)
	ep, err := newLocalEndpoint(dir)
	require.NoError(t, err)

	backend := &dialCountBackend{}
	connector := containerConnector{backend: backend, host: "engine", endpoint: ep}

	// Nothing listens yet: the exec tunnel is used.
	conn, err := connector.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 1, backend.dials)

	// The engine answers on the port and checks the token: dialed directly.
	inner, err := net.Listen("tcp", ep.addr)
	require.NoError(t, err)
	l := engine.NewTokenListener(inner, ep.token)
	defer l.Close()
	echoed := make(chan string, 1)
	go func() {
		c, err := l.Accept()
		if err != nil {
			return
		}
		defer c.Close()
		buf := make([]byte, 5)
		n, _ := c.Read(buf)
		echoed <- string(buf[:n])
	}()
	conn, err = connector.Connect(t.Context())
	require.NoError(t, err)
	_, err = conn.Write([]byte("hello"))
	require.NoError(t, err)
	require.Equal(t, "hello", <-echoed)
	conn.Close()
	require.Equal(t, 1, backend.dials)

	// A wrong token never reaches the engine; the connector falls back.
	wrong := connector
	wrong.endpoint.token = strings.Repeat("0", 64)
	conn, err = wrong.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	// The dial itself succeeds (the listener closes after reading the
	// preamble), so this asserts the token gate, not the fallback.
}

func TestLocalEndpointDirRefusesRemoteDaemon(t *testing.T) {
	endpointTestEnv(t)
	t.Setenv("DOCKER_HOST", "tcp://build-host:2376")
	_, ok := localEndpointDir("dagger-engine-remote")
	require.False(t, ok)
}
