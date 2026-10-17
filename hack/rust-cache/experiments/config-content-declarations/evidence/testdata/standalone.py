from pathlib import Path
import hashlib
import json
import subprocess
import time

root = Path(__file__).parent
work = Path('/tmp/dagger-config-declarations-only')
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
target = work/'core/workspace'
(target/'git_client_config_cache_test.go').write_bytes((root/'git_client_config_cache_test.go').read_bytes())
rows = []

def run(label, command):
    started = time.monotonic()
    with (root/('standalone-'+label+'.log')).open('w') as out:
        result = subprocess.run(command, cwd=work, stdout=out, stderr=subprocess.STDOUT)
    rows.append(dict(label=label, command=command, cwd=str(work), exit_code=result.returncode,
                     seconds=time.monotonic()-started))
    (root/'standalone-validation.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(label, result.returncode, flush=True)
    assert result.returncode == 0, label

run('baseline-race', [go, 'test', '-p', '2', '-race', '-count=1', './core/workspace'])
run('apply', ['git', 'apply', '--exclude=core/workspace/git_client_config_cache_test.go', str(root/'candidate.patch')])
bench = (root/'git_client_config_cache_bench_test.go').read_text()
bench = bench.replace('data, err := os.ReadFile(os.Getenv("DAGGER_DECLARATIONS_BENCH_CONFIG"))',
    'fixture := os.Getenv("DAGGER_DECLARATIONS_BENCH_CONFIG")\n if fixture == "" { fixture = "testdata/git-client-declarations.toml" }\n data, err := os.ReadFile(fixture)')
(target/'git_client_config_cache_bench_test.go').write_text(bench)
fixture = target/'testdata/git-client-declarations.toml'
fixture.parent.mkdir(exist_ok=True)
fixture.write_bytes((root/'real-module.toml').read_bytes())
run('format', ['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt', '-w', str(target/'git_client_config_cache_bench_test.go')])
run('candidate-race', [go, 'test', '-p', '2', '-race', '-count=1', './core/workspace'])
run('benchmark-values', [go, 'test', '-p', '2', '-run', '^$', '-bench', '^BenchmarkGitClientDeclarations$', '-benchtime=1x', '-count=1', './core/workspace'])
files = ['sdk_scopes.go', 'git_clients.go', 'git_client_config_cache.go',
         'git_client_config_cache_test.go', 'git_client_config_cache_bench_test.go',
         'testdata/git-client-declarations.toml']
(root/'standalone-source-hashes.json').write_text(json.dumps({name: hashlib.sha256((target/name).read_bytes()).hexdigest()
                                                          for name in files}, indent=2)+'\n')
