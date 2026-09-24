#!/usr/bin/env python3
"""Create an isolated project for bench-artifact-discovery.py.

Default: a Go SDK module with nested collections and many shared check paths.
With --go-module: install that local dagger.io/go checkout and generate Go tests.
The destination must not exist. A Git boundary prevents scans escaping into a
parent workspace. Neither fixture executes tests during `check -l --all`.
"""

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--go-module", type=Path)
    args = parser.parse_args()
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=False)
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    def write(path, contents):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)

    if args.go_module:
        write(".discovery-benchmark-fixture", "go\n")
        # TOML literal strings preserve filesystem paths without shell expansion.
        source = str(args.go_module.resolve())
        if "'" in source or "\n" in source:
            parser.error("module path cannot contain single quotes or newlines")
        write("dagger.toml", f"""[modules.go]
source = '{source}'

[modules.dang-sdk]
source = "github.com/dagger/dang-sdk@collections"

[sdks.dang]
module = "dang-sdk"
""")
        for module in range(8):
            write(f"m{module}/go.mod", f"module example.com/m{module}\n\ngo 1.26.1\n")
            for package in range(16):
                source = 'package sample\n\nimport "testing"\n\n'
                source += "".join(f"func TestCase{package}_{test}(t *testing.T) {{}}\n" for test in range(8))
                write(f"m{module}/pkg{package:02}/sample_test.go", source)
    else:
        write("dagger.toml", '[modules.bench]\nsource = "./bench"\nentrypoint = true\n')
        write("bench/dagger.json", '{"name":"bench","engineVersion":"v1.0.0","sdk":{"source":"go"},"source":"."}\n')
        source = '''package main
import "dagger/bench/internal/dagger"
type Bench struct{}
func (*Bench) Modules() *Modules { return &Modules{Names: []string{"m0","m1","m2","m3","m4","m5","m6","m7"}} }
// +collection
type Modules struct {
    // +keys
    Names []string
}
func (*Modules) Get(key string) *Unit { return &Unit{Name:key} }
type Unit struct { Name string }
func (*Unit) Tests() *Tests { return &Tests{Names: []string{"t0","t1","t2","t3"}} }
// +collection
type Tests struct {
    // +keys
    Names []string
}
func (*Tests) Get(key string) *Case { return &Case{Name:key} }
type Case struct { Name string }
func (*Case) Broken() *dagger.Container { panic("leaf must stay deferred") }
'''
        source += "".join(f"// +check\nfunc (*Case) Check{i}() error {{ return nil }}\n" for i in range(16))
        write("bench/main.go", source)
    print(root)


if __name__ == "__main__":
    main()
