package drivers

import (
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/adrg/xdg"
	"github.com/stretchr/testify/require"

	"github.com/dagger/dagger/engine"
)

// endpointTestEnv gives the driver a private state dir and a local daemon.
func endpointTestEnv(t *testing.T) {
	t.Helper()
	dir, err := os.MkdirTemp("", "dagger-state")
	require.NoError(t, err)
	t.Cleanup(func() { os.RemoveAll(dir) })
	t.Setenv("XDG_STATE_HOME", dir)
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

	// The token file is private and its directory mounted read-only; the
	// port is loopback only.
	info, err := os.Stat(filepath.Join(dir, endpointTokenFile))
	require.NoError(t, err)
	require.Equal(t, os.FileMode(0o600), info.Mode().Perm())
	require.Contains(t, backend.runOpts.volumes, dir+":"+endpointDirInContainer+":ro")
	require.Contains(t, backend.runOpts.ports, "127.0.0.1:"+port+":"+port)
	require.Equal(t, []string{
		"--debug", "--debugaddr", defaultDebugListenerAddress,
		"--token-addr", "tcp://0.0.0.0:" + port, "--token-file", endpointDirInContainer + "/" + endpointTokenFile,
	}, backend.runOpts.args)
	got := connector.(containerConnector).endpoint
	require.NotNil(t, got)
	require.Equal(t, ep.addr, got.addr)
	require.Equal(t, ep.token, got.token)
}

func TestContainerConnectorPrefersLocalEndpoint(t *testing.T) {
	endpointTestEnv(t)
	dir, ok := localEndpointDir("dagger-engine-ep")
	require.True(t, ok)
	ep, err := newLocalEndpoint(dir)
	require.NoError(t, err)

	// The engine answers on the port behind the handshake.
	inner, err := net.Listen("tcp", ep.addr)
	require.NoError(t, err)
	accepts := &countingListener{Listener: inner}
	l := engine.NewTokenListener(accepts, ep.token)
	defer l.Close()
	echoed := make(chan string, 1)
	go func() {
		for {
			c, err := l.Accept()
			if err != nil {
				return
			}
			buf := make([]byte, 5)
			n, _ := c.Read(buf)
			echoed <- string(buf[:n])
			c.Close()
		}
	}()

	// Dialed directly: no exec tunnel.
	backend := &dialCountBackend{}
	connector := containerConnector{backend: backend, host: "engine", endpoint: ep}
	conn, err := connector.Connect(t.Context())
	require.NoError(t, err)
	_, err = conn.Write([]byte("hello"))
	require.NoError(t, err)
	require.Equal(t, "hello", <-echoed)
	conn.Close()
	require.Equal(t, 0, backend.dials)

	// A wrong token fails the handshake: the connector falls back to the
	// exec tunnel and does not dial the port again in this process.
	wrong := containerConnector{backend: backend, host: "engine", endpoint: &localEndpoint{addr: ep.addr, token: strings.Repeat("0", 64)}}
	before := accepts.count.Load()
	conn, err = wrong.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 1, backend.dials)
	require.Equal(t, before+1, accepts.count.Load())
	conn, err = wrong.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 2, backend.dials)
	require.Equal(t, before+1, accepts.count.Load())

	// Nothing listening at all (engine recreated without the endpoint,
	// or a record left by an older container): exec tunnel.
	l.Close()
	none := containerConnector{backend: backend, host: "engine", endpoint: &localEndpoint{addr: ep.addr, token: ep.token}}
	conn, err = none.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 3, backend.dials)
	require.True(t, none.endpoint.down.Load())

	// A fresh endpoint (its container was just created) is not given up
	// on: the engine is still starting.
	fresh := containerConnector{backend: backend, host: "engine", endpoint: &localEndpoint{addr: ep.addr, token: ep.token, fresh: true}}
	conn, err = fresh.Connect(t.Context())
	require.NoError(t, err)
	conn.Close()
	require.Equal(t, 4, backend.dials)
	require.False(t, fresh.endpoint.down.Load())
}

// countingListener counts accepted connections.
type countingListener struct {
	net.Listener
	count atomic.Int64
}

func (l *countingListener) Accept() (net.Conn, error) {
	c, err := l.Listener.Accept()
	if err == nil {
		l.count.Add(1)
	}
	return c, err
}

func TestLocalEndpointDirRefusesRemoteDaemon(t *testing.T) {
	endpointTestEnv(t)
	t.Setenv("DOCKER_HOST", "tcp://build-host:2376")
	_, ok := localEndpointDir("dagger-engine-remote")
	require.False(t, ok)
}
