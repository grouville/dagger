from pathlib import Path
import json, os, re, secrets, subprocess, time
base=Path('/tmp/rust-cache-sipsma-review')
root=base/'native-fingerprint-import-trace'
root.mkdir(exist_ok=False)
raw=Path('/tmp/rust-cache-oct13-filter/local-receiver/telemetry.jsonl')
source=Path('/tmp/rust-native-config-entry-1026-after')
config=source/'dagger.toml'
original=config.read_text()
filename=source/'leaf_1023/src/lib.rs'
s,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',filename.read_text())
assert count==1
filename.write_text(s)
start=raw.stat().st_size
try:
    s,count=re.subn(r'source = "[^"]+"','source = "/tmp/dagger-rust-native-package-fingerprint"',original,count=1)
    assert count==1
    config.write_text(s)
    env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()+':43183')
    with (root/'check.log').open('w') as out:
        result=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','rust:packages/check'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
    assert result.returncode==0
    end=raw.stat().st_size
    assert end-start<64*1024*1024, end-start
    with raw.open('rb') as f:
        f.seek(start)
        capture=f.read(end-start)
    (root/'telemetry.jsonl').write_bytes(capture)
    (root/'window.json').write_text(json.dumps(dict(start=start,end=end,bytes=end-start,source=str(raw),bounded=True),indent=2)+'\n')
    spans={}
    for line in capture.splitlines():
        row=json.loads(line)
        if row.get('kind')=='span' and 'Host.directory' in row.get('name',''):
            spans[row['spanId']]=row
    (root/'host-directory-spans.json').write_text(json.dumps(list(spans.values()),indent=2)+'\n')
    for row in spans.values():
        print(json.dumps(row)[:2400])
finally:config.write_text(original)
