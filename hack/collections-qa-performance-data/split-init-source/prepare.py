#!/usr/bin/env python3
"""Prepare source only. Never builds, tests, queries engines or modifies checkout."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess

ROOT = Path('/home/dagger/dag')
LAB = Path(__file__).resolve().parent
SRC = LAB / 'source'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)

original = (ROOT / 'cmd/init/main.go').read_text()
imports = '''//go:build linux

package main

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

    "github.com/dagger/dagger/engine/distconsts"
)

func main() {
    if os.Args[0] != "/.init" {
        return
    }
    if err := mainInit(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}

'''
light = imports + original[original.index('func mainInit() error {'):original.index('func mainSession() error {')]
light = replace_once(light, 'func startSessionSubprocess() error {\n', '''func startSessionSubprocess() error {
    return startSessionCommand(exec.Command(distconsts.DaggerSessionContainerPath))
}

// Keep attachables in a separate process: PID1's global reaper must not race
// the exec.Cmd children owned by Git and other session providers.
func startSessionCommand(cmd *exec.Cmd) error {
''')
light = replace_once(light, '\t// start the session subprocess\n\tcmd := exec.Command("/proc/self/exe")\n\n', '')

heavy = replace_once(original, '\t"github.com/dagger/dagger/engine/client/secretprovider"\n', '\t"github.com/dagger/dagger/engine/client/secretprovider"\n\t"github.com/dagger/dagger/engine/distconsts"\n')
heavy = replace_once(heavy, 'case "/proc/self/exe":', 'case "/proc/self/exe", distconsts.DaggerSessionContainerPath:')

constants = (ROOT / 'engine/distconsts/consts.go').read_text()
constants = replace_once(constants, '\tDaggerInitPath = "/usr/local/bin/dagger-init"\n', '''\tDaggerInitPath = "/usr/local/bin/dagger-init"
    DaggerInitLitePath = "/usr/local/bin/dagger-init-lite"
    DaggerSessionContainerPath = "/.dagger-session"
''')

executor = (ROOT / 'engine/engineutil/executor_spec.go').read_text()
executor = replace_once(executor, 'Src:      hostBindMount{srcPath: distconsts.DaggerInitPath},', 'Src:      hostBindMount{srcPath: distconsts.DaggerInitLitePath},')
executor = replace_once(executor, '\tstate.procInfo.Meta.Args = append([]string{initPath}, state.procInfo.Meta.Args...)', '''    // The helper keeps provider subprocesses separate from the PID1 reaper.
    // Mount it even for non-nested execs to preserve explicit session-env behavior.
    state.mounts = append(state.mounts, executor.Mount{
        Src: hostBindMount{srcPath: distconsts.DaggerInitPath},
        Dest: distconsts.DaggerSessionContainerPath,
        Readonly: true,
    })
\tstate.procInfo.Meta.Args = append([]string{initPath}, state.procInfo.Meta.Args...)''')

builder = (ROOT / '.dagger/modules/engine-dev/build/builder.go').read_text()
builder = replace_once(builder, '\t\t{path: consts.DaggerInitPath, file: build.daggerInit()},', '\t\t{path: consts.DaggerInitPath, file: build.daggerInit()},\n\t\t{path: distconsts.DaggerInitLitePath, file: build.binary("./cmd/init-lite", false)},')

files = {
    'cmd/init-lite/main.go': light,
    'cmd/init/main.go': heavy,
    'engine/distconsts/consts.go': constants,
    'engine/engineutil/executor_spec.go': executor,
    '.dagger/modules/engine-dev/build/builder.go': builder,
}
for name, data in files.items():
    p = SRC / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data)

# Formatting only; this does not compile or execute the prototype.
gofmt = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt'
subprocess.run([gofmt, '-w', *[str(SRC / n) for n in files]], check=True)

overlay = {'Replace': {str(ROOT / n): str(SRC / n) for n in files}}
(LAB / 'source-overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
patch = []
manifest = {'status': 'prepared only; not built or tested', 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'inputs': {}}
for name in files:
    before = (ROOT / name).read_bytes() if (ROOT / name).exists() else b''
    after = (SRC / name).read_bytes()
    manifest['inputs'][name] = {'before_sha256': sha(before) if before else None, 'after_sha256': sha(after)}
    patch.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile='a/' + name if before else '/dev/null', tofile='b/' + name))
(LAB / 'prototype.patch').write_text(''.join(patch))
(LAB / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
