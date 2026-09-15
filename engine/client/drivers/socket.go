package drivers

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/adrg/xdg"

	"github.com/dagger/dagger/engine/distconsts"
	"github.com/dagger/dagger/engine/slog"
)

// engineSocketDirInContainer is where the engine listens on its unix socket
// (the directory of distconsts.DefaultEngineSockAddr).
const engineSocketDirInContainer = "/run/dagger"

// engineSocketDir returns a private host directory to bind-mount over the
// engine's socket directory, so the client can dial the engine directly
// instead of tunnelling every connection through `docker exec`. Only a
// local Linux daemon can share a unix socket with the client; elsewhere,
// and when the daemon turns out to be remote, the connector falls back to
// the exec tunnel because the socket never appears.
//
// The socket grants what `docker exec` into the engine grants, so the
// directory must be reachable by the caller alone: it lives under the
// caller's runtime directory and is refused unless it is a plain directory
// the caller owns with no group or other permissions. Otherwise another
// local user could substitute their own socket and receive the session.
func engineSocketDir(containerName string) (string, bool) {
	if runtime.GOOS != "linux" || containerName == "" || xdg.RuntimeDir == "" || !localDockerDaemon() {
		return "", false
	}
	dir := filepath.Join(xdg.RuntimeDir, "dagger", containerName)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", false
	}
	return dir, privateDir(dir)
}

// localDockerDaemon reports whether the container runtime runs on this
// host, which a shared unix socket requires. DOCKER_HOST unset or a unix
// socket means local; anything else (tcp, ssh, a context) is treated as
// remote so no directory is created on another machine.
func localDockerDaemon() bool {
	host := os.Getenv("DOCKER_HOST")
	return host == "" || strings.HasPrefix(host, "unix://")
}

// privateDir reports whether path is a directory owned by the caller that
// nobody else can enter, following no symlink.
func privateDir(path string) bool {
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() {
		return false
	}
	if info.Mode().Perm()&0o077 != 0 {
		return false
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(st.Uid) == os.Getuid()
}

// engineSocketArgs makes the engine's unix sockets connectable by the
// client's group. The socket lives in a directory only the client's user
// can enter, so this grants nothing beyond what `docker exec` already does.
func engineSocketArgs() []string {
	return []string{"--group", strconv.Itoa(os.Getgid())}
}

// dialEngineSocket dials the engine socket shared into socketDir, if any.
func dialEngineSocket(ctx context.Context, socketDir string) (net.Conn, bool) {
	if socketDir == "" {
		return nil, false
	}
	path := filepath.Join(socketDir, filepath.Base(distconsts.DefaultEngineSockAddr))
	if _, err := os.Stat(path); err != nil {
		return nil, false
	}
	conn, err := (&net.Dialer{Timeout: time.Second}).DialContext(ctx, "unix", path)
	if err != nil {
		slog.Debug("engine socket not dialable, using the exec tunnel", "path", path, "error", err)
		return nil, false
	}
	return conn, true
}
