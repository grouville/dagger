package drivers

import (
	"bufio"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/stretchr/testify/require"
)

// fakeDaemon serves the handful of Docker Engine API routes the backend
// uses. Exec streams echo stdin to stdout, with a stderr frame first, in
// the multiplexed format a non-TTY attach uses.
func fakeDaemon(t *testing.T) (*dockerAPI, *fakeDaemonState) {
	t.Helper()
	state := &fakeDaemonState{containers: map[string]bool{}}
	mux := http.NewServeMux()
	mux.HandleFunc("/_ping", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("API-Version", "1.47")
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/containers/json", func(w http.ResponseWriter, r *http.Request) {
		var list []map[string]any
		for name := range state.containers {
			list = append(list, map[string]any{"Id": name, "Names": []string{"/" + name}})
		}
		json.NewEncoder(w).Encode(list)
	})
	mux.HandleFunc("/containers/", func(w http.ResponseWriter, r *http.Request) {
		rest := strings.TrimPrefix(r.URL.Path, "/containers/")
		name, op, _ := strings.Cut(rest, "/")
		running, ok := state.containers[name]
		if !ok {
			http.Error(w, `{"message":"no such container"}`, http.StatusNotFound)
			return
		}
		switch op {
		case "json":
			json.NewEncoder(w).Encode(map[string]any{"Id": name, "Name": "/" + name, "State": map[string]any{"Running": running}})
		case "start":
			state.starts++
			state.containers[name] = true
			w.WriteHeader(http.StatusNoContent)
		case "exec":
			state.execs++
			var opts struct{ AttachStdin bool }
			_ = json.NewDecoder(r.Body).Decode(&opts)
			state.execStdin = opts.AttachStdin
			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]any{"Id": "exec-1"})
		default:
			http.NotFound(w, r)
		}
	})
	mux.HandleFunc("/exec/exec-1/json", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"ID": "exec-1", "Running": false, "ExitCode": 0})
	})
	mux.HandleFunc("/exec/exec-1/start", func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.Copy(io.Discard, r.Body) // the daemon reads the options before switching protocols
		conn, rw, err := w.(http.Hijacker).Hijack()
		require.NoError(t, err)
		defer conn.Close()
		_, _ = rw.WriteString("HTTP/1.1 101 UPGRADED\r\nContent-Type: application/vnd.docker.raw-stream\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n")
		require.NoError(t, rw.Flush())
		stdout := stdcopy.NewStdWriter(conn, stdcopy.Stdout)
		stderr := stdcopy.NewStdWriter(conn, stdcopy.Stderr)
		_, _ = stderr.Write([]byte("noise on stderr\n"))
		if !state.execStdin {
			return // nothing to echo; the exec ends like a command would
		}
		buf := make([]byte, 4096)
		for {
			n, err := rw.Read(buf)
			if n > 0 {
				_, _ = stdout.Write(buf[:n])
			}
			if err != nil {
				return
			}
		}
	})
	// The API version prefix is stripped by a wrapper.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if i := strings.Index(r.URL.Path, "/v1."); i == 0 {
			if j := strings.Index(r.URL.Path[1:], "/"); j > 0 {
				r.URL.Path = r.URL.Path[j+1:]
			}
		}
		mux.ServeHTTP(w, r)
	}))
	t.Cleanup(srv.Close)
	backend := newDockerAPI(client.WithHost("tcp://" + srv.Listener.Addr().String()))
	return backend, state
}

type fakeDaemonState struct {
	containers map[string]bool
	starts     int
	execs      int
	execStdin  bool
}

func TestDockerAPIBackend(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	backend, state := fakeDaemon(t)
	state.containers["dagger-engine-v0.21.0"] = false

	available, err := backend.Available(ctx)
	require.NoError(t, err)
	require.True(t, available)

	names, err := backend.ContainerLs(ctx)
	require.NoError(t, err)
	require.Equal(t, []string{"dagger-engine-v0.21.0"}, names)

	exists, err := backend.ContainerExists(ctx, "dagger-engine-v0.21.0")
	require.NoError(t, err)
	require.True(t, exists)
	exists, err = backend.ContainerExists(ctx, "dagger-engine-other")
	require.NoError(t, err)
	require.False(t, exists)

	require.NoError(t, backend.ContainerStart(ctx, "dagger-engine-v0.21.0"))
	require.Equal(t, 1, state.starts)

	// The dial is an attached exec: bytes round-trip, stderr never shows.
	conn, err := backend.ContainerDial(ctx, "dagger-engine-v0.21.0", []string{"buildctl", "dial-stdio"})
	require.NoError(t, err)
	defer conn.Close()
	_, err = conn.Write([]byte("hello engine\n"))
	require.NoError(t, err)
	line, err := bufio.NewReader(conn).ReadString('\n')
	require.NoError(t, err)
	require.Equal(t, "hello engine\n", line)
	require.Equal(t, 1, state.execs)

	stdout, _, err := backend.ContainerExec(ctx, "dagger-engine-v0.21.0", []string{"true"})
	require.NoError(t, err)
	require.Equal(t, "", stdout)
}

func TestDockerAPIBackendUnavailableDaemon(t *testing.T) {
	t.Parallel()
	dead, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	addr := dead.Addr().String()
	dead.Close()

	backend := newDockerAPI(client.WithHost("tcp://" + addr))
	available, err := backend.Available(t.Context())
	require.NoError(t, err)
	require.False(t, available, "a daemon that does not answer leaves the choice to the CLI backend")
}

var _ io.Reader = (*execConn)(nil)
