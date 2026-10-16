import collections
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

base = Path('/tmp/rust-cache-sipsma-review')
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--module',required=True)
parser.add_argument('--name',required=True)
args=parser.parse_args()
root=base/('cache-object-retention-'+args.name)
source = root / 'source'
module=Path(args.module)
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16275', RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'), _EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'), RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
cli = ['python3', str(base / 'local_cli_collector.py')]
root.mkdir(exist_ok=False)
shutil.copytree(base / 'native-hint-retention/source', source,
                ignore=shutil.ignore_patterns('.git', 'target', 'dagger.toml', 'dagger.lock'))
part = source / 'app/src/part_0000.rs'
original = part.read_text()
sequence = secrets.randbits(48)
rows = []


def command(label, args, cwd=module):
    log = root / (label + '.log')
    with log.open('w') as output:
        result = subprocess.run(cli + args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, (label, result.returncode)
    return log


def build(label, hits):
    command(label, ['api', 'with-session', '--', str(base / 'native-batch-runtime-inspect'),
                    '-automatic-cache', '-cache-key', 'cache-object-retention-'+args.name, '-expected-actions', '4',
                    '-expected-hits', str(hits), '-source', str(source), 'check', str(root / 'unused-state')])
    assert not (root / 'unused-state').exists()


def query(label, document):
    path = root / (label + '.graphql')
    path.write_text(document + '\n')
    result=root/(label+'-response.json')
    command(label,['api','with-session','--','python3',str(base/'query_session_json.py'),str(path),str(result)],source)
    return json.loads(result.read_text())


def snapshot(label):
    deadline = time.monotonic() + 30
    while True:
        with urllib.request.urlopen('http://127.0.0.1:16103/debug/dagql/cache', timeout=30) as response:
            data = response.read((128<<20)+1)
            assert len(data)<=128<<20,'cache snapshot exceeds 128 MiB diagnostic limit'
        value = json.loads(data)
        if not value.get('session_results'):
            break
        assert time.monotonic() < deadline, 'CLI sessions did not release before the capture'
        time.sleep(0.25)
    (root / (label + '.json')).write_bytes(data)
    nodes = {node['shared_result_id']: node for node in value['results']}
    caches = [node for node in nodes.values() if node.get('type_name') == 'RustCompilerCache']
    latest = max(caches, key=lambda node: node['shared_result_id']) if caches else None
    seen, pending = set(), [latest['shared_result_id']] if latest else []
    while pending:
        number = pending.pop()
        if number in seen:
            continue
        seen.add(number)
        pending.extend(nodes.get(number, {}).get('explicit_dep_ids', []))
    links = {link['RefKey'] for number in seen for link in nodes.get(number, {}).get('snapshot_links', [])}
    identities = {}
    for number in seen:
        for identity, size in nodes.get(number, {}).get('cache_usage_size_by_identity', {}).items():
            identities[identity] = max(identities.get(identity, 0), size)
    adjacency = {number: set(node.get('explicit_dep_ids', [])) for number, node in nodes.items()}
    pairs = [(number, child) for number, children in adjacency.items() for child in children
             if number < child and number in adjacency.get(child, set())]
    rust_types = {'RustCompilerCache', 'RustCompilerCompilation', 'RustNativeCache', 'RustNativeCompilation'}
    row = {'label': label, 'results': len(nodes), 'latest_cache': latest['shared_result_id'] if latest else None,
           'closure_results': len(seen), 'snapshot_refs': len(links),
           'all_snapshot_refs': len({link['RefKey'] for node in nodes.values() for link in node.get('snapshot_links', [])}),
           'known_usage_bytes': sum(identities.values()), 'mutual_ownership_pairs': len(pairs),
           'rust_results': {name: sum(node.get('type_name') == name for node in nodes.values()) for name in sorted(rust_types)},
           'closure_types': dict(collections.Counter(nodes[number].get('type_name', '') for number in seen if number in nodes))}
    rows.append(row)
    (root / 'summary.json').write_text(json.dumps(rows, indent=2) + '\n')
    print({key: row[key] for key in ['label', 'results', 'closure_results', 'snapshot_refs', 'mutual_ownership_pairs', 'rust_results']}, flush=True)
    assert row['mutual_ownership_pairs'] == 0, row
    return row


try:
    build('cold', 0)
    query('prune-initial', '{engine{localCache{prune}}}')
    snapshot('initial-pruned')
    build('after-initial-prune', 4)
    for i in range(1, 21):
        sequence += 1
        text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {sequence};', original)
        assert count == 1
        part.write_text(text)
        build(f'edit-{i}', 3)
        if i in [5, 10, 20]:
            query(f'prune-{i}', '{engine{localCache{prune}}}')
            snapshot(f'edit-{i}-pruned')
            build(f'after-prune-{i}', 4)
    query('final-usage', '{engine{localCache{entrySet{entryCount diskSpaceBytes}}}}')

finally:
    part.write_text(original)
