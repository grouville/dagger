from pathlib import Path
import json
import os
import re
import secrets
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'native-discovery-current-compile-validation-final'
root.mkdir(exist_ok=False)
source = root/'workspace'
shutil.copytree('/tmp/rust-native-config-entry-small-after', source,
                ignore=shutil.ignore_patterns('.git', 'target', 'dagger.toml', 'dagger.lock'))
subprocess.run(['git','init','--quiet',str(source)],check=True)
nonce = secrets.token_hex(12)
key = 'native-discovery-current-compile-' + nonce
module = Path('/tmp/dagger-rust-native-discovery-current')
image = 'rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42'
(source/'Cargo.toml').write_text('# unique validation '+nonce+'\n'+(source/'Cargo.toml').read_text())
(source/'dagger.toml').write_text(
    '[modules.rust]\nsource = '+json.dumps(str(module))+
    '\n[modules.rust.settings]\nimage = '+json.dumps(image)+
    '\nlocked = true\nnativeCache = true\ncacheKey = '+json.dumps(key)+'\n')
env = {k:v for k,v in os.environ.items()
       if k not in ['DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE']
       and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           DAGGER_CLOUD_TOKEN='local-benchmark-token',
           _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',
           XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',
           RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
rows=[]

def invoke(label, selection='rust:packages/check', failure=False):
    command=[str(base/'dagger-artifact-list-buffered'),'check',selection]
    with (root/(label+'.log')).open('w') as output:
        p=subprocess.run(command,cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
    log=(root/(label+'.log')).read_text()
    assert bool(p.returncode)==failure,(label,p.returncode)
    if failure:
        assert 'error' in log.lower() and 'exit code: 1' in log,label
    else:
        assert 'passed' in log,label
    rows.append(dict(label=label,command=command,returncode=p.returncode,expected_failure=failure))
    (root/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('PASS',label,flush=True)

def retained(label, actions, batch_actions):
    command=['python3',str(base/'local_cli_collector.py'),'api','with-session','--',
             str(base/'native-batch-runtime-inspect'),'-automatic-cache','-cache-key',key,
             '-expected-actions',str(actions),'-expected-hits',str(actions),
             '-expected-batch-actions',str(batch_actions),'-inspect-cache',str(root/(label+'.cache.json')),
             '-source',str(source),'check',str(base/'root-projection-no-host-state')]
    with (root/(label+'.log')).open('w') as output:
        p=subprocess.run(command,cwd=module,env=env,stdout=output,stderr=subprocess.STDOUT)
    assert p.returncode==0,(label,p.returncode)
    rows.append(dict(label=label,actions=actions,hits=actions,current_batch_actions=batch_actions))
    (root/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('PASS',label,'reuses',actions,'of',actions,'actions',flush=True)

original=(source/'app/src/lib.rs').read_text()
invoke('cold-collection')
retained('cold-result-reused',2,2)
edit,count=re.subn(r'pub fn edited_value\(\) -> u64 \{ \d+ \}',
                  'pub fn edited_value() -> u64 { '+str(secrets.randbits(48))+' }',original)
assert count==1
(source/'app/src/lib.rs').write_text(edit)
invoke('edited-collection')
retained('edited-result-reused',2,1)
(source/'app/src/lib.rs').write_text('this is not valid Rust\n')
invoke('invalid-rust-collection',failure=True)
(source/'app/src/lib.rs').write_text(edit)
invoke('repaired-collection')
retained('repaired-result-reused',2,1)
(source/'app/src/lib.rs').write_text(original)
invoke('reverted-collection')
retained('reverted-result-reused',2,2)
invoke('direct-check',selection='rust:check')
retained('direct-result-reused',2,2)
