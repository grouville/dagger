package drivers

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
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
func engineSocketDir(containerName string) (string, bool) {
	if runtime.GOOS != "linux" || containerName == "" {
		return "", false
	}
	base := xdg.RuntimeDir
	if base == "" {
		base = filepath.Join(os.TempDir(), "dagger-"+strconv.Itoa(os.Getuid()))
	}
	dir := filepath.Join(base, "dagger", containerName)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", false
	}
	return dir, true
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
