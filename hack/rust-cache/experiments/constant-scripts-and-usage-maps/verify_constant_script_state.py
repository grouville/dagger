from pathlib import Path
import json
import os
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'constant-script-state'
root.mkdir(exist_ok=False)
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
summary = {}
objects = {}
scripts = {}
for variant, module in [('before','/tmp/dagger-rust-local-package-fingerprint'),
                        ('after','/tmp/dagger-rust-constant-script-getters')]:
    copy = root/('module-'+variant)
    shutil.copytree(module, copy, ignore=shutil.ignore_patterns('.git'))
    p = copy/'main.dang'
    text = p.read_text()
    marker = 'type Rust {\n'
    assert text.count(marker)==1
    method = '''  pub serializedProject(source: Directory!): String! {
    let scripts = JSON.encode([cargoLayoutProbe, layoutSelect, publishLegacyArtifacts])
    let collection = JSON.encode(packages(source: source))
    JSON.encode([scripts, collection])
  }
'''
    p.write_text(text.replace(marker, marker+method))
    command = ['python3', str(base/'local_cli_collector.py'), 'api','with-session','--',
               str(base/'rust-packages-state-inspect'),'-native-cache',
               '-cache-key','constant-script-state','-source','/tmp/rust-native-package-fingerprint-smoke']
    log = root/(variant+'.log')
    with log.open('w') as output:
        result = subprocess.run(command,cwd=copy,env=env,stdout=output,stderr=subprocess.STDOUT)
    assert result.returncode==0,(variant,result.returncode)
    encoded=next(json.loads(line) for line in log.read_text().splitlines() if line.startswith('"['))
    script_text,collection_text=json.loads(encoded)
    scripts[variant]=json.loads(script_text)
    objects[variant]=json.loads(collection_text)['project']
    (root/(variant+'-scripts.json')).write_text(json.dumps(scripts[variant],indent=2)+'\n')
    (root/(variant+'-state.json')).write_text(json.dumps(objects[variant],indent=2)+'\n')
    summary[variant]=dict(bytes=len(json.dumps(objects[variant],separators=(',',':')).encode()),
                          keys=sorted(objects[variant]),script_bytes=sum(len(s.encode()) for s in scripts[variant]))
    print('PASS',variant,summary[variant],flush=True)
assert scripts['before']==scripts['after'],'computed properties changed executable script bytes'
constants=['cargoLayoutProbe','layoutSelect','publishLegacyArtifacts']
assert all(k in objects['before'] and k not in objects['after'] for k in constants)
assert {k:v for k,v in objects['before'].items() if k not in constants}==objects['after'],'non-script project state changed'
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS exact script bytes and non-script project state preserved',flush=True)
