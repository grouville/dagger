package drivers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
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
// Nothing changes for remote daemons: the port would be on another host, so
// no endpoint is created and the exec tunnel is used as before.
const (
	endpointTokenFile   = "token"
	endpointPortFile    = "port"
	endpointTokenInPath = "/run/dagger/token"
)

type localEndpoint struct {
	addr  string
	token string
}

// localEndpointDir returns the private directory holding the endpoint files
// for containerName, creating it if needed. It refuses a directory that is
// not a plain directory owned by the caller with mode 0700.
func localEndpointDir(containerName string) (string, bool) {
	if containerName == "" || !localDockerDaemon() {
		return "", false
	}
	base := xdg.RuntimeDir
	if base == "" {
		base = filepath.Join(xdg.StateHome, "dagger")
	}
	dir := filepath.Join(base, "dagger", "engines", containerName)
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

// privateDir reports whether path is a directory owned by the caller that
// nobody else can enter, following no symlink.
func privateDir(path string) bool {
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0o077 != 0 {
		return false
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(st.Uid) == os.Getuid()
}

// newLocalEndpoint picks a free loopback port and a fresh token and records
// both for later commands. It is called only when a container is created.
func newLocalEndpoint(dir string) (localEndpoint, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return localEndpoint{}, err
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return localEndpoint{}, err
	}
	token := hex.EncodeToString(raw)
	if err := os.WriteFile(filepath.Join(dir, endpointTokenFile), []byte(token+"\n"), 0o600); err != nil {
		return localEndpoint{}, err
	}
	if err := os.WriteFile(filepath.Join(dir, endpointPortFile), []byte(strconv.Itoa(port)+"\n"), 0o600); err != nil {
		return localEndpoint{}, err
	}
	return localEndpoint{addr: net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), token: token}, nil
}

// loadLocalEndpoint reads the endpoint recorded for containerName, if any.
func loadLocalEndpoint(dir string) (localEndpoint, bool) {
	token, err := os.ReadFile(filepath.Join(dir, endpointTokenFile))
	if err != nil {
		return localEndpoint{}, false
	}
	port, err := os.ReadFile(filepath.Join(dir, endpointPortFile))
	if err != nil {
		return localEndpoint{}, false
	}
	p, err := strconv.Atoi(strings.TrimSpace(string(port)))
	if err != nil || p <= 0 {
		return localEndpoint{}, false
	}
	return localEndpoint{addr: net.JoinHostPort("127.0.0.1", strconv.Itoa(p)), token: strings.TrimSpace(string(token))}, true
}

func (ep localEndpoint) valid() bool { return ep.addr != "" && ep.token != "" }

// dial connects to the endpoint and presents the token.
func (ep localEndpoint) dial(ctx context.Context) (net.Conn, error) {
	d := net.Dialer{Timeout: time.Second}
	conn, err := d.DialContext(ctx, "tcp", ep.addr)
	if err != nil {
		return nil, err
	}
	if err := engine.WriteEndpointToken(conn, ep.token); err != nil {
		conn.Close()
		return nil, err
	}
	return conn, nil
}

// probe reports whether an engine answers on the endpoint right now.
func (ep localEndpoint) probe(ctx context.Context) bool {
	if !ep.valid() {
		return false
	}
	conn, err := ep.dial(ctx)
	if err != nil {
		slog.Debug("engine endpoint not dialable, using the exec tunnel", "addr", ep.addr, "error", err)
		return false
	}
	conn.Close()
	return true
}

// runOptionsForEndpoint publishes the engine's TCP listener on the loopback
// port and hands it the token file.
func (ep localEndpoint) runOptions(dir string, opts *runOpts) {
	_, port, _ := net.SplitHostPort(ep.addr)
	opts.ports = append(opts.ports, fmt.Sprintf("127.0.0.1:%s:%s", port, port))
	opts.volumes = append(opts.volumes, filepath.Join(dir, endpointTokenFile)+":"+endpointTokenInPath+":ro")
	opts.args = append(opts.args, "--addr", "tcp://0.0.0.0:"+port, "--token-file", endpointTokenInPath)
}
