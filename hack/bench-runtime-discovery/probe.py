#!/usr/bin/env python3
"""Read-only runtime discovery attribution, not a Dagger CLI benchmark."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import time
import urllib.parse

OWNER = Path(__file__).resolve().parent
CUSTOM = 'dagger-stream-relay-2uzdettn-r2'
PREFIX = 'dagger-engine-'
PATTERN = '^/?(' + re.escape(PREFIX) + '.*|' + re.escape(CUSTOM) + ')$'

class UnixHTTP(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=10)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')

def request(path):
    start = time.perf_counter_ns()
    conn = UnixHTTP()
    try:
        conn.request('GET', path)
        response = conn.getresponse()
        headers_ns = time.perf_counter_ns() - start
        body = response.read()
        assert response.status == 200, response.status
    finally:
        conn.close()
    return json.loads(body), {'wall_ns': time.perf_counter_ns() - start,
                              'headers_ns': headers_ns, 'response_bytes': len(body)}

def select(names):
    return sorted(n for n in names if n.startswith(PREFIX) or n == CUSTOM)

def main():
    out = OWNER / 'run'
    out.mkdir()
    env = {k:v for k,v in os.environ.items() if k not in ['DOCKER_HOST', 'DOCKER_CONTEXT']}
    command = ['docker', '--host', 'unix:///var/run/docker.sock']
    version, _ = request('/version')
    api_version = version['ApiVersion']
    assert re.fullmatch(r'1\.[0-9]+', api_version)
    commands = {
        'version': ['version', '--format', '{{.Client.Version}} {{.Server.Version}}'],
        'all_names': ['ps', '-a', '--format', '{{.Names}}'],
        'filtered_names': ['ps', '-a', '--format', '{{.Names}}', '--filter', 'name=' + PATTERN],
        'filtered_states': ['ps', '-a', '--format', '{{.Names}}\t{{.State}}', '--filter', 'name=' + PATTERN],
        'exact_inspect': ['container', 'inspect', CUSTOM, '--format', '{{.Name}}\t{{.State.Status}}'],
    }
    endpoint = f'/v{api_version}/containers/json?' + urllib.parse.urlencode({
        'all': '1', 'filters': json.dumps({'name': [PATTERN]}, separators=(',', ':'))})
    with (out / 'provenance.json').open('x') as f:
        json.dump({'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'docker_version': version['Version'], 'api_version': api_version,
                   'commands': {k:command+v for k,v in commands.items()},
                   'http_path': endpoint, 'scope':'read-only local runtime attribution'}, f, indent=2)
    rows = []
    expected_selected = None
    expected_all = None
    def invoke(kind, cycle):
        nonlocal expected_selected, expected_all
        if kind == 'api_filtered':
            data, timing = request(endpoint)
            names = sorted(n.removeprefix('/') for c in data for n in c['Names'])
            states = {n.removeprefix('/'): c['State'] for c in data for n in c['Names']}
            row = dict(kind=kind, cycle=cycle, names=names, states=states, **timing)
        else:
            start = time.perf_counter_ns()
            p = subprocess.run(command+commands[kind], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            wall = time.perf_counter_ns() - start
            assert p.returncode == 0 and not p.stderr, (kind, p.returncode, p.stderr.decode())
            text = p.stdout.decode()
            row = dict(kind=kind, cycle=cycle, wall_ns=wall, stdout=text)
            if kind in ['filtered_states', 'exact_inspect']:
                state_rows = [line.split('\t') for line in text.splitlines()]
                assert all(len(r) == 2 for r in state_rows)
                states = {r[0].removeprefix('/'):r[1] for r in state_rows}
                names = sorted(states)
                row.update(names=names, states=states)
            elif kind != 'version':
                names = sorted(text.splitlines())
                row['names'] = names
        rows.append(row)
        with (out / 'rows.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
        if kind not in ['version', 'exact_inspect']:
            selected = select(row['names'])
            assert CUSTOM in selected
            if expected_selected is None:
                expected_selected = selected
            assert selected == expected_selected, ('selected inventory changed', kind)
            if kind == 'all_names':
                if expected_all is None:
                    expected_all = row['names']
                assert expected_all == row['names'], 'full inventory changed'
            else:
                assert row['names'] == expected_selected, 'filter returned extras'
            if 'states' in row:
                assert row['states'][CUSTOM] == 'running', 'retained target changed state'
        if kind == 'exact_inspect':
            assert row['names'] == [CUSTOM] and row['states'][CUSTOM] == 'running'

    invoke('all_names', 0)
    kinds = list(commands) + ['api_filtered']
    for cycle in range(1, 9):
        order = kinds if cycle % 2 else list(reversed(kinds))
        for kind in order:
            invoke(kind, cycle)
        print(f'cycle {cycle}/8 complete; inventory parity passed', flush=True)
    invoke('all_names', 9)
    summary = {}
    for kind in kinds:
        values = [r['wall_ns']/1e6 for r in rows if r['kind'] == kind and 1 <= r['cycle'] <= 8]
        summary[kind] = {'median_ms':statistics.median(values), 'range_ms':[min(values),max(values)], 'n':len(values)}
    with (out / 'summary.json').open('x') as f:
        json.dump({'summaries':summary, 'selected':expected_selected, 'full_count':len(expected_all)}, f, indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
