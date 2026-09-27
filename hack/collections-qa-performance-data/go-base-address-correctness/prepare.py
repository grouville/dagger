#!/usr/bin/env python3
"""Prepare a NEW owned correctness workspace; does not invoke Dagger or Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/tmp/collections-perf/go-base-address-retained-v1')
p = argparse.ArgumentParser()
p.add_argument('--module-file', type=Path, required=True)
p.add_argument('--module-sha256', required=True)
p.add_argument('--workspace', type=Path, required=True)
a = p.parse_args()
workspace = a.workspace.resolve()
assert workspace.parent == ROOT and workspace.name.startswith('workspace-')
assert not workspace.exists()
source = a.module_file.read_bytes()
assert hashlib.sha256(source).hexdigest() == a.module_sha256
assert b'baseAddress: Address' in source
shutil.copytree(ROOT/'fixture', workspace)
workspace.chmod(0o700)
(workspace/'.witness-owned').write_text('go-base-address-retained-v1\n')
module = workspace/'.dagger/perf-go'
module.mkdir(parents=True)
(module/'go.dang').write_bytes(source)
(module/'dagger-module.toml').write_text('''name = "go"
engineVersion = "v1.0.0-beta.13"
[runtime]
source = "dang"
[[dependencies]]
name = "gomod"
source = "github.com/dagger/go/gomod@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de"
''')
# Bound workspace traversal before starting an engine. No commit or git identity.
subprocess.run(['git','init','-q',str(workspace)], check=True, timeout=10)
subprocess.run(['git','-C',str(workspace),'add','-f','.'], check=True, timeout=10)
manifest = {str(f.relative_to(workspace)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in workspace.rglob('*') if f.is_file() and '.git' not in f.relative_to(workspace).parts}
(ROOT/(workspace.name+'-manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
