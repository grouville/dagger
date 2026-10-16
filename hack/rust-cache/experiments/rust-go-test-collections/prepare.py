from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).parent
fixtures = root / 'fixtures'
fixtures.mkdir(exist_ok=True)
rust_module = Path('/tmp/dagger-rust-native-discovery-current')
go_module = Path('/tmp/dagger-go-official-collections-oct16')
rust_bin = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
records = []
for language in ['rust', 'go']:
    for count in [1, 16, 64]:
        source = fixtures / f'{language}-{count}'
        source.mkdir(exist_ok=False)
        subprocess.run(['git', 'init', '--quiet', str(source)], check=True)
        if language == 'rust':
            names = [f'pkg_{i:03d}' for i in range(count)]
            (source / 'Cargo.toml').write_text('[workspace]\nmembers = ' + json.dumps(names) + '\nresolver = "2"\n')
            for name in names:
                package = source / name
                (package / 'src').mkdir(parents=True)
                (package / 'Cargo.toml').write_text(f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n\n[lib]\ndoctest = false\n')
                (package / 'src/lib.rs').write_text('pub fn edited_value() -> u64 { 1 }\n' + ''.join(f'#[test]\nfn test_{i:03d}() {{ assert!(edited_value() > 0); }}\n' for i in range(8)))
            (source / 'dagger.toml').write_text(f'[modules.rust]\nsource = "{rust_module}"\n[modules.rust.settings]\nimage = "rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42"\nlocked = true\nnativeCache = true\ncacheKey = "rust-go-test-collections-{count}"\n')
            subprocess.run([str(rust_bin / 'cargo'), 'generate-lockfile', '--offline'], cwd=source, check=True, stdout=subprocess.DEVNULL)
            edit_file = source / 'pkg_000/src/lib.rs'
        else:
            (source / 'go.mod').write_text('module example.com/testcollections\n\ngo 1.26.6\n')
            for i in range(count):
                package = source / f'pkg_{i:03d}'
                package.mkdir()
                (package / 'value.go').write_text('package testcollections\n\nfunc EditedValue() uint64 { return 1 }\n')
                (package / 'value_test.go').write_text('package testcollections\nimport "testing"\n' + ''.join(f'func Test{i:03d}(t *testing.T) {{ if EditedValue() == 0 {{ t.Fatal("zero") }} }}\n' for i in range(8)))
            (source / 'dagger.toml').write_text(f'[modules.go]\nsource = "{go_module}"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\n')
            edit_file = source / 'pkg_000/value.go'
        records.append(dict(language=language, packages=count, tests=count * 8, source=str(source), edit_file=str(edit_file)))
(root / 'fixtures.json').write_text(json.dumps(records, indent=2) + '\n')
provenance = {}
for name, module in [('rust', rust_module), ('go', go_module)]:
    provenance[name] = dict(path=str(module), revision=subprocess.check_output(['git', '-C', str(module), 'rev-parse', 'HEAD'], text=True).strip(), dirty=subprocess.check_output(['git', '-C', str(module), 'status', '--porcelain'], text=True))
(root / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print('Prepared six isolated workspaces; eight real tests per package', flush=True)
