package drivers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	telemetry "github.com/dagger/otel-go"
	"github.com/docker/cli/cli/config"
	"github.com/docker/cli/cli/connhelper"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/docker/docker/errdefs"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/opencontainers/go-digest"
	"go.opentelemetry.io/otel"
)

// dockerAPI is the docker backend for everything on the per-command path:
// finding, starting and connecting to the engine container. It talks to the
// daemon's API directly, so each of those costs what the daemon charges
// (a few ms) rather than a `docker` process spawn (30-40ms each; a command
// spawned six or seven). Provisioning (pull, create, remove, image load) is
// rare and stays on the embedded CLI backend, which keeps its credential
// and flag semantics untouched.
type dockerAPI struct {
	docker

	once sync.Once
	cli  *client.Client
	err  error
	opts []client.Opt
}

var _ containerBackend = (*dockerAPI)(nil)

func newDockerAPI(opts ...client.Opt) *dockerAPI {
	return &dockerAPI{docker: docker{cmd: "docker"}, opts: opts}
}

// reset forgets the resolved daemon client so the next use resolves the
// endpoint again; tests change DOCKER_HOST between cases.
func (d *dockerAPI) reset() {
	d.once = sync.Once{}
	d.cli, d.err = nil, nil
}

// api returns the daemon client, resolving the endpoint the way the docker
// CLI does: DOCKER_HOST, else DOCKER_CONTEXT or the config file's current
// context (read from the CLI's context store, TLS material included), else
// the platform default socket.
func (d *dockerAPI) api() (*client.Client, error) {
	d.once.Do(func() {
		opts := d.opts
		if opts == nil {
			opts, d.err = dockerEndpointOpts()
			if d.err != nil {
				return
			}
		}
		opts = append(opts, client.WithAPIVersionNegotiation())
		d.cli, d.err = client.NewClientWithOpts(opts...)
	})
	return d.cli, d.err
}

const (
	dockerDefaultContext = "default"
	dockerEnvContext     = "DOCKER_CONTEXT"
)

// dockerEndpointOpts resolves the daemon endpoint the way the docker CLI
// does, without its context packages (they would pull a second client
// module into the build): DOCKER_HOST wins; otherwise DOCKER_CONTEXT or the
// config file's current context is read from the CLI's context store on
// disk (contexts/meta/<sha256(name)>/meta.json, TLS files under
// contexts/tls/<sha256(name)>/docker/); otherwise the platform default.
func dockerEndpointOpts() ([]client.Opt, error) {
	if host := os.Getenv(client.EnvOverrideHost); host != "" {
		return dockerHostOpts(host, "")
	}
	name := os.Getenv(dockerEnvContext)
	if name == "" {
		if cfg := config.LoadDefaultConfigFile(io.Discard); cfg != nil {
			name = cfg.CurrentContext
		}
	}
	if name == "" || name == dockerDefaultContext {
		return dockerHostOpts(client.DefaultDockerHost, "")
	}
	ctxDir := digest.FromString(name).Encoded()
	metaPath := filepath.Join(config.ContextStoreDir(), "meta", ctxDir, "meta.json")
	raw, err := os.ReadFile(metaPath)
	if err != nil {
		return nil, fmt.Errorf("docker context %q: %w", name, err)
	}
	var meta struct {
		Endpoints map[string]struct {
			Host string `json:"Host"`
		} `json:"Endpoints"`
	}
	if err := json.Unmarshal(raw, &meta); err != nil {
		return nil, fmt.Errorf("docker context %q: %w", name, err)
	}
	ep, ok := meta.Endpoints["docker"]
	if !ok || ep.Host == "" {
		return nil, fmt.Errorf("docker context %q has no docker endpoint", name)
	}
	return dockerHostOpts(ep.Host, filepath.Join(config.ContextStoreDir(), "tls", ctxDir, "docker"))
}

// dockerHostOpts turns a daemon host into client options: ssh:// (and the
// other connection helpers) dial through the helper, tcp:// picks up TLS
// material from tlsDir when present, sockets need nothing.
func dockerHostOpts(host, tlsDir string) ([]client.Opt, error) {
	helper, err := connhelper.GetConnectionHelper(host)
	if err != nil {
		return nil, err
	}
	if helper != nil {
		return []client.Opt{client.WithHost(helper.Host), client.WithDialContext(helper.Dialer)}, nil
	}
	opts := []client.Opt{client.WithHost(host)}
	if tlsDir != "" {
		ca, cert, key := filepath.Join(tlsDir, "ca.pem"), filepath.Join(tlsDir, "cert.pem"), filepath.Join(tlsDir, "key.pem")
		if _, err := os.Stat(cert); err == nil {
			opts = append(opts, client.WithTLSClientConfig(ca, cert, key))
		}
	}
	return opts, nil
}

func (d *dockerAPI) span(ctx context.Context, name string) (context.Context, func(*error)) {
	ctx, span := otel.Tracer("").Start(ctx, "docker api "+name, telemetry.Encapsulated())
	return ctx, func(err *error) { telemetry.EndWithCause(span, err) }
}

// Available pings the daemon with a short bound. A daemon that does not
// answer leaves the choice to the CLI backend, which reports the friendly
// "no runtime" error exactly as before.
func (d *dockerAPI) Available(ctx context.Context) (available bool, rerr error) {
	cli, err := d.api()
	if err != nil {
		return false, nil //nolint:nilerr // not available; the CLI backend explains
	}
	ctx, end := d.span(ctx, "ping")
	defer end(&rerr)
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	if _, err := cli.Ping(ctx); err != nil {
		return false, nil //nolint:nilerr // same
	}
	return true, nil
}

func (d *dockerAPI) ContainerExists(ctx context.Context, name string) (exists bool, rerr error) {
	cli, err := d.api()
	if err != nil {
		return false, err
	}
	ctx, end := d.span(ctx, "inspect "+name)
	defer end(&rerr)
	if _, err := cli.ContainerInspect(ctx, name); err != nil {
		if errdefs.IsNotFound(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func (d *dockerAPI) ContainerLs(ctx context.Context) (names []string, rerr error) {
	cli, err := d.api()
	if err != nil {
		return nil, err
	}
	ctx, end := d.span(ctx, "list")
	defer end(&rerr)
	containers, err := cli.ContainerList(ctx, container.ListOptions{All: true})
	if err != nil {
		return nil, err
	}
	for _, c := range containers {
		for _, n := range c.Names {
			names = append(names, strings.TrimPrefix(n, "/"))
		}
	}
	return names, nil
}

func (d *dockerAPI) ContainerStart(ctx context.Context, name string) (rerr error) {
	cli, err := d.api()
	if err != nil {
		return err
	}
	ctx, end := d.span(ctx, "start "+name)
	defer end(&rerr)
	return cli.ContainerStart(ctx, name, container.StartOptions{})
}

func (d *dockerAPI) ContainerExec(ctx context.Context, name string, args []string) (stdout, stderr string, rerr error) {
	cli, err := d.api()
	if err != nil {
		return "", "", err
	}
	ctx, end := d.span(ctx, "exec "+strings.Join(args, " "))
	defer end(&rerr)
	exec, err := cli.ContainerExecCreate(ctx, name, container.ExecOptions{
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          args,
	})
	if err != nil {
		return "", "", err
	}
	resp, err := cli.ContainerExecAttach(ctx, exec.ID, container.ExecAttachOptions{})
	if err != nil {
		return "", "", err
	}
	defer resp.Close()
	var outBuf, errBuf bytes.Buffer
	if _, err := stdcopy.StdCopy(&outBuf, &errBuf, resp.Reader); err != nil {
		return "", "", err
	}
	inspect, err := cli.ContainerExecInspect(ctx, exec.ID)
	if err != nil {
		return "", "", err
	}
	// Trimmed like the CLI backend's captured output.
	stdout, stderr = strings.TrimSpace(outBuf.String()), strings.TrimSpace(errBuf.String())
	if inspect.ExitCode != 0 {
		return stdout, stderr, fmt.Errorf("exit status %d: %s", inspect.ExitCode, stderr)
	}
	return stdout, stderr, nil
}

// ContainerDial runs args in the container with stdin and stdout attached
// and returns the attached stream as a connection, the same tunnel
// `docker exec -i` gives, without the process.
func (d *dockerAPI) ContainerDial(ctx context.Context, name string, args []string) (_ net.Conn, rerr error) {
	cli, err := d.api()
	if err != nil {
		return nil, err
	}
	ctx, end := d.span(ctx, "dial "+name)
	defer end(&rerr)
	exec, err := cli.ContainerExecCreate(ctx, name, container.ExecOptions{
		AttachStdin:  true,
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          args,
	})
	if err != nil {
		return nil, err
	}
	resp, err := cli.ContainerExecAttach(ctx, exec.ID, container.ExecAttachOptions{})
	if err != nil {
		return nil, err
	}
	return newExecConn(resp), nil
}

// execConn adapts a hijacked exec stream to net.Conn. Writes go straight to
// the daemon; reads see the demultiplexed stdout, stderr is dropped.
type execConn struct {
	resp types.HijackedResponse
	out  *io.PipeReader
}

func newExecConn(resp types.HijackedResponse) *execConn {
	pr, pw := io.Pipe()
	go func() {
		_, err := stdcopy.StdCopy(pw, io.Discard, resp.Reader)
		if err == nil {
			err = io.EOF
		}
		pw.CloseWithError(err)
	}()
	return &execConn{resp: resp, out: pr}
}

func (c *execConn) Read(p []byte) (int, error)  { return c.out.Read(p) }
func (c *execConn) Write(p []byte) (int, error) { return c.resp.Conn.Write(p) }
func (c *execConn) Close() error {
	c.resp.Close()
	return c.out.Close()
}
func (c *execConn) LocalAddr() net.Addr                { return c.resp.Conn.LocalAddr() }
func (c *execConn) RemoteAddr() net.Addr               { return c.resp.Conn.RemoteAddr() }
func (c *execConn) SetDeadline(t time.Time) error      { return c.resp.Conn.SetDeadline(t) }
func (c *execConn) SetReadDeadline(t time.Time) error  { return c.resp.Conn.SetReadDeadline(t) }
func (c *execConn) SetWriteDeadline(t time.Time) error { return c.resp.Conn.SetWriteDeadline(t) }
