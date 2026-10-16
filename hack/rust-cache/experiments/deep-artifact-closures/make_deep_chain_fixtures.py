"""Generate path-only Cargo workspaces with a real chain of dependencies."""
import argparse
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--sizes', nargs='+', type=int, default=[32, 512])
args = parser.parse_args()
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
image = 'rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42'
modules = {'before': '/tmp/dagger-rust-native-worker-request-current',
           'after': '/tmp/dagger-rust-native-deep-artifact-closures',
           'cargo': '/tmp/dagger-rust-native-worker-request-current'}
env = dict(os.environ, RUSTC=str(toolchain/'rustc'), RUSTDOC=str(toolchain/'rustdoc'))
for size in args.sizes:
    assert size >= 2
    members = [f'pkg_{i:04d}' for i in range(size-1)]+['app']
    for variant, module in modules.items():
        root = Path(f'/tmp/rust-native-deep-chain-{size}-{variant}')
        root.mkdir(exist_ok=False)
        (root/'Cargo.toml').write_text('[workspace]\nresolver = "2"\nmembers = '+json.dumps(members)+'\n')
        for i, name in enumerate(members):
            folder = root/name
            (folder/'src').mkdir(parents=True)
            manifest = '[package]\nname = '+json.dumps(name)+'\nversion = "0.1.0"\nedition = "2021"\n'
            if i:
                previous = members[i-1]
                manifest += '\n[dependencies]\n'+previous+' = { path = "../'+previous+'" }\n'
            (folder/'Cargo.toml').write_text(manifest)
            if name == 'app':
                text = f'fn main() {{ println!("{{}}", {members[i-1]}::value()); }}\n'
                filename = 'main.rs'
            else:
                value = 'EDIT' if i == 0 else members[i-1]+'::value().wrapping_add(EDIT)'
                text = 'pub const EDIT: u64 = 1;\npub fn value() -> u64 { '+value+' }\n'
                filename = 'lib.rs'
            (folder/'src'/filename).write_text(text)
        (root/'dagger.toml').write_text('[modules.rust]\nsource = '+json.dumps(module)+'\n[modules.rust.settings]\nimage = '+json.dumps(image)+'\nlocked = true\nnativeCache = true\ncacheKey = '+json.dumps(f'native-deep-chain-{size}-{variant}')+'\n')
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run([str(toolchain/'cargo'), 'generate-lockfile', '--offline'], cwd=root, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(root, 'packages', size, 'initial binary output', size-1, flush=True)
