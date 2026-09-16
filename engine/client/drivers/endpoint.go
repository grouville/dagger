package drivers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/adrg/xdg"

	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/slog"
)

// A local engine gets its own authenticated endpoint: when the client
// creates the container it publishes the engine's TCP listener on a loopback
// port and protects it with a token it generates, so later commands connect
// directly instead of tunnelling every connection through `docker exec`
// (which costs the daemon a runc exec per connection). The token lives in a
// directory only the caller can enter, which is the same boundary docker
// group membership gives: another local user cannot read it.
//
// The directory is under the user's state home, not the runtime dir: the
// container outlives reboots (docker restarts it) and its bind mount must
// still find the token. The engine is handed the directory rather than the
// file, so a directory that went missing turns into an empty one and the
// engine starts without its endpoint instead of failing to start; the
// client then uses the exec tunnel for that engine.
//
// Nothing changes for remote daemons: the port would be on another host, so
// no endpoint is created and the exec tunnel is used as before.
const (
	endpointTokenFile      = "token"
	endpointPortFile       = "port"
	endpointDirInContainer = "/run/dagger/endpoint"
)

type localEndpoint struct {
	addr  string
	token string
	// fresh marks an endpoint published for a container created by this
	// process, whose engine may still be starting.
	fresh bool
	// down is set once a dial to an established endpoint fails; see connect.
	down atomic.Bool
}

// endpointStateDir is where the endpoint files for containerName live.
func endpointStateDir(containerName string) string {
	return filepath.Join(xdg.StateHome, "dagger", "engines", containerName)
}

// localEndpointDir returns the private directory holding the endpoint files
// for containerName, creating it if needed. It refuses a directory that is
// not a plain directory owned by the caller with mode 0700.
func localEndpointDir(containerName string) (string, bool) {
	if containerName == "" || !localDockerDaemon() {
		return "", false
	}
	dir := endpointStateDir(containerName)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", false
	}
	return dir, privateDir(dir)
}

// localDockerDaemon reports whether the container runtime runs on this
// host. DOCKER_HOST unset or a unix socket means local; anything else (tcp,
// ssh) is treated as remote.
func localDockerDaemon() bool {
	host := os.Getenv("DOCKER_HOST")
	return host == "" || strings.HasPrefix(host, "unix://")
}

// newLocalEndpoint picks a free loopback port and a fresh token and records
// both for later commands. It is called only when a container is created.
func newLocalEndpoint(dir string) (*localEndpoint, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, err
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return nil, err
	}
	token := hex.EncodeToString(raw)
	if err := os.WriteFile(filepath.Join(dir, endpointTokenFile), []byte(token+"\n"), 0o600); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(dir, endpointPortFile), []byte(strconv.Itoa(port)+"\n"), 0o600); err != nil {
		return nil, err
	}
	return &localEndpoint{addr: net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), token: token, fresh: true}, nil
}

// forgetLocalEndpoint removes a recorded endpoint that no engine will
// ever answer on, so later commands go straight to the exec tunnel.
func forgetLocalEndpoint(dir string) {
	os.Remove(filepath.Join(dir, endpointTokenFile))
	os.Remove(filepath.Join(dir, endpointPortFile))
}

// removeLocalEndpointState drops the files recorded for a container that
// was removed.
func removeLocalEndpointState(containerName string) {
	if containerName == "" {
		return
	}
	os.RemoveAll(endpointStateDir(containerName))
}

// loadLocalEndpoint reads the endpoint recorded for containerName, if any.
func loadLocalEndpoint(dir string) (*localEndpoint, bool) {
	token, err := os.ReadFile(filepath.Join(dir, endpointTokenFile))
	if err != nil {
		return nil, false
	}
	port, err := os.ReadFile(filepath.Join(dir, endpointPortFile))
	if err != nil {
		return nil, false
	}
	p, err := strconv.Atoi(strings.TrimSpace(string(port)))
	if err != nil || p <= 0 {
		return nil, false
	}
	return &localEndpoint{addr: net.JoinHostPort("127.0.0.1", strconv.Itoa(p)), token: strings.TrimSpace(string(token))}, true
}

// dial connects to the endpoint and completes the handshake.
func (ep *localEndpoint) dial(ctx context.Context) (net.Conn, error) {
	d := net.Dialer{Timeout: time.Second}
	conn, err := d.DialContext(ctx, "tcp", ep.addr)
	if err != nil {
		return nil, err
	}
	if err := engine.EndpointHandshake(conn, ep.token, engine.EndpointHandshakeTimeout); err != nil {
		conn.Close()
		return nil, err
	}
	return conn, nil
}

// probe reports whether an engine answers on the endpoint right now.
func (ep *localEndpoint) probe(ctx context.Context) bool {
	conn, err := ep.dial(ctx)
	if err != nil {
		slog.Debug("engine endpoint not dialable, using the exec tunnel", "addr", ep.addr, "error", err)
		return false
	}
	conn.Close()
	return true
}

// connect dials the endpoint unless an earlier dial in this process
// failed: an established endpoint that stopped answering is not retried
// on every connection, the exec tunnel takes over for good. A fresh
// endpoint is retried, its engine is still starting.
func (ep *localEndpoint) connect(ctx context.Context) (net.Conn, bool) {
	if ep == nil || ep.down.Load() {
		return nil, false
	}
	conn, err := ep.dial(ctx)
	if err != nil {
		if !ep.fresh {
			ep.down.Store(true)
		}
		slog.Debug("engine endpoint not answering, using the exec tunnel", "addr", ep.addr, "error", err)
		return nil, false
	}
	return conn, true
}

// runOptions publishes the engine's TCP listener on the loopback port and
// hands it the endpoint directory.
func (ep *localEndpoint) runOptions(dir string, opts *runOpts) {
	_, port, _ := net.SplitHostPort(ep.addr)
	opts.ports = append(opts.ports, fmt.Sprintf("127.0.0.1:%s:%s", port, port))
	opts.volumes = append(opts.volumes, dir+":"+endpointDirInContainer+":ro")
	opts.args = append(opts.args, "--token-addr", "tcp://0.0.0.0:"+port, "--token-file", path.Join(endpointDirInContainer, endpointTokenFile))
}
