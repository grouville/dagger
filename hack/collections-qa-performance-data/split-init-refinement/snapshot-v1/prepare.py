from pathlib import Path
import difflib, hashlib, json, subprocess

ROOT = Path('/home/dagger/dag')
HERE = Path(__file__).resolve().parent
OLD = Path('/tmp/collections-perf/split-init-prototype-v1')
SRC = HERE / 'source'
original = (ROOT / 'cmd/init/main.go').read_text()
def replace_once(s, a, b):
    assert s.count(a) == 1, a
    return s.replace(a, b)

# Keep the signal/session/TTY/reaping body identical except its helper parameter.
pid1 = original[original.index('func mainInit() error {'):original.index('func mainSession() error {')]
pid1 = replace_once(pid1, 'func mainInit() error {', '''// Run starts and supervises the container payload. It must run in its own
// process: its global child reaper must not share a process with providers
// which use exec.Cmd.Wait. sessionHelper names the separate attachables binary.
func Run(sessionHelper string) error {''')
pid1 = replace_once(pid1, 'if err := startSessionSubprocess(); err != nil {', 'if err := startSessionSubprocess(sessionHelper); err != nil {')
pid1 = replace_once(pid1, 'func startSessionSubprocess() error {', '''func startSessionSubprocess(sessionHelper string) error {
    return startSessionCommand(exec.Command(sessionHelper))
}

func startSessionCommand(cmd *exec.Cmd) error {''')
pid1 = replace_once(pid1, '\t// start the session subprocess\n\tcmd := exec.Command("/proc/self/exe")\n\n', '')
shared = '''//go:build linux

// Package initexec supervises the payload process without importing providers
// or engine provisioning into the PID1 executable.
package initexec

import (
    "errors"
    "fmt"
    "io"
    "os"
    "os/exec"
    "os/signal"
    "path/filepath"
    "syscall"
    "time"

    "golang.org/x/sys/unix"
)

''' + pid1
heavy = original[:original.index('func mainInit() error {')] + original[original.index('func mainSession() error {'):]
for dep in ['errors', 'io', 'os/exec', 'os/signal', 'path/filepath', 'syscall', 'time']:
    heavy = replace_once(heavy, '\t"' + dep + '"\n', '')
heavy = replace_once(heavy, '\n\t"golang.org/x/sys/unix"\n', '')
heavy = replace_once(heavy, '\t"github.com/dagger/dagger/engine"', '\t"github.com/dagger/dagger/engine"\n\t"github.com/dagger/dagger/engine/distconsts"\n\t"github.com/dagger/dagger/engine/session/initexec"')
heavy = replace_once(heavy, 'err = mainInit()', 'err = initexec.Run("/proc/self/exe")')
heavy = replace_once(heavy, 'case "/proc/self/exe":', 'case "/proc/self/exe", distconsts.DaggerSessionContainerPath:')
lite = '''//go:build linux

package main

import (
    "fmt"
    "os"

    "github.com/dagger/dagger/engine/distconsts"
    "github.com/dagger/dagger/engine/session/initexec"
)

func main() {
    if os.Args[0] != "/.init" {
        return
    }
    if err := initexec.Run(distconsts.DaggerSessionContainerPath); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
'''
constants = replace_once((ROOT / 'engine/distconsts/consts.go').read_text(), '\tDaggerInitPath = "/usr/local/bin/dagger-init"\n', '\tDaggerInitPath = "/usr/local/bin/dagger-init"\n\tDaggerInitLitePath = "/usr/local/bin/dagger-init-lite"\n\tDaggerSessionContainerPath = "/.dagger-session"\n')
executor = replace_once((ROOT / 'engine/engineutil/executor_spec.go').read_text(), 'Src:      hostBindMount{srcPath: distconsts.DaggerInitPath},', 'Src:      hostBindMount{srcPath: distconsts.DaggerInitLitePath},')
executor = replace_once(executor, '\tstate.procInfo.Meta.Args = append([]string{initPath}, state.procInfo.Meta.Args...)', '''    // Providers own their child processes separately from PID1's global reaper.
    // Keep the helper available for explicit session-env use on ordinary execs.
    state.mounts = append(state.mounts, executor.Mount{
        Src: hostBindMount{srcPath: distconsts.DaggerInitPath},
        Dest: distconsts.DaggerSessionContainerPath,
        Readonly: true,
    })
\tstate.procInfo.Meta.Args = append([]string{initPath}, state.procInfo.Meta.Args...)''')
builder = replace_once((ROOT / '.dagger/modules/engine-dev/build/builder.go').read_text(), '\t\t{path: consts.DaggerInitPath, file: build.daggerInit()},', '\t\t{path: consts.DaggerInitPath, file: build.daggerInit()},\n\t\t{path: distconsts.DaggerInitLitePath, file: build.binary("./cmd/init-lite", false)},')
tests = (OLD / 'source/cmd/init-lite/main_test.go').read_text().replace('package main', 'package initexec').replace('mainInit()', 'Run("/unused-session-helper")')
tests = replace_once(tests, '\t"time"\n', '\t"time"\n\n\t"github.com/creack/pty"\n\t"golang.org/x/sys/unix"\n')
tests += '''
// A real controlling terminal exercises detach/reattach and resize delivery.
// The payload checks its own session and foreground process group, then waits
// for a resize and the forwarded termination signal. No host process is used.
func TestSplitInitTTY(t *testing.T) {
    dir := t.TempDir()
    ready, resized := filepath.Join(dir, "ready"), filepath.Join(dir, "resized")
    ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
    defer cancel()
    cmd := splitInitProcessContext(ctx, "init", "tty", ready, resized)
    cmd.Cancel = func() error { return cmd.Process.Signal(syscall.SIGTERM) }
    cmd.WaitDelay = 15*time.Second
    terminal, err := pty.StartWithSize(cmd, &pty.Winsize{Rows: 24, Cols: 80})
    if err != nil { t.Fatal(err) }
    defer terminal.Close()
    t.Cleanup(func() {
        if cmd.ProcessState == nil {
            _ = cmd.Process.Signal(syscall.SIGTERM)
            _ = cmd.Wait()
        }
    })
    if err := waitSplitInitFile(ready); err != nil { t.Fatal(err) }
    if err := pty.Setsize(terminal, &pty.Winsize{Rows: 31, Cols: 101}); err != nil { t.Fatal(err) }
    if err := cmd.Process.Signal(syscall.SIGWINCH); err != nil { t.Fatal(err) }
    if err := waitSplitInitFile(resized); err != nil { t.Fatal(err) }
    if err := cmd.Process.Signal(syscall.SIGTERM); err != nil { t.Fatal(err) }
    var exit *exec.ExitError
    if err := cmd.Wait(); !errors.As(err, &exit) || exit.ExitCode() != 42 {
        t.Fatalf("TTY payload did not finish after forwarded termination: %v", err)
    }
}
'''
tests = replace_once(tests, '\tswitch args[0] {\n', '''\tswitch args[0] {
    case "tty":
        sid, err := unix.Getsid(0)
        foreground, foregroundErr := unix.IoctlGetInt(0, unix.TIOCGPGRP)
        initial, sizeErr := pty.GetsizeFull(os.Stdin)
        if err != nil || foregroundErr != nil || sizeErr != nil || sid != os.Getpid() || foreground != os.Getpid() || initial.Rows != 24 || initial.Cols != 80 { os.Exit(82) }
        ch := make(chan os.Signal, 4)
        signal.Notify(ch, syscall.SIGWINCH, syscall.SIGTERM)
        if err := os.WriteFile(args[1], []byte("ready"), 0o600); err != nil { os.Exit(83) }
        timeout := time.After(15*time.Second)
        for {
            select {
            case sig := <-ch:
                if sig == syscall.SIGTERM { os.Exit(42) }
                size, err := pty.GetsizeFull(os.Stdin)
                if err == nil && size.Rows == 31 && size.Cols == 101 {
                    if err := os.WriteFile(args[2], []byte("resized"), 0o600); err != nil { os.Exit(84) }
                }
            case <-timeout: os.Exit(85)
            }
        }
''')
files = {
    'engine/session/initexec/init.go': shared,
    'engine/session/initexec/init_test.go': tests,
    'cmd/init/main.go': heavy,
    'cmd/init-lite/main.go': lite,
    'engine/distconsts/consts.go': constants,
    'engine/engineutil/executor_spec.go': executor,
    'engine/engineutil/init_split_test.go': (OLD / 'source/engine/engineutil/init_split_test.go').read_text(),
    '.dagger/modules/engine-dev/build/builder.go': builder,
}
for name, source in files.items():
    path = SRC / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
subprocess.run(['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt', '-w', *[str(SRC / name) for name in files]], check=True)
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = {'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), 'status':'source only', 'originals':{}, 'sources':{}}
patch = []
for name in files:
    before = (ROOT / name).read_bytes() if (ROOT / name).is_file() else b''
    after = (SRC / name).read_bytes()
    manifest['originals'][name] = sha(before) if before else None
    manifest['sources'][name] = sha(after)
    patch += difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile='a/'+name if before else '/dev/null',tofile='b/'+name)
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(HERE/'prototype.patch').write_text(''.join(patch))
(HERE/'overlay.json').write_text(json.dumps({'Replace':{str(ROOT/name):str(SRC/name)for name in files}},indent=2)+'\n')
print(json.dumps({'files':len(files),'engine_calls':0,'cloud_calls':0}))
