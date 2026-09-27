#!/usr/bin/env python3
"""Source-only prepared witness; run within ONE reviewed local Dagger SDK session.
No lifecycle, engine selection, dependency preparation, or public Cloud setup here.
The caller supplies an isolated fixture and an already reviewed local-only session.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

ROOT = Path('/tmp/collections-perf/go-base-address-retained-v1')
p = argparse.ArgumentParser()
p.add_argument('--workspace', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()
workspace = a.workspace.resolve()
assert workspace.parent == ROOT and workspace.name.startswith('workspace-')
assert a.output.resolve().parent == ROOT and not a.output.exists()
assert (workspace / '.witness-owned').read_text() == 'go-base-address-retained-v1\n'
assert os.environ.get('DO_NOT_TRACK') == '1'
assert not any(k in os.environ for k in ('DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL'))
# with-session injects its LOCAL telemetry proxy even when Cloud is disabled.
# The standard-library probe emits no OTLP. Validate the injected destinations.
proxy_ports = set()
for key, value in os.environ.items():
    if key.startswith('OTEL_') and key.endswith('_ENDPOINT'):
        endpoint = urlsplit(value)
        assert endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1'
        assert endpoint.username is None and endpoint.password is None
        assert not endpoint.query and not endpoint.fragment
        assert endpoint.path in ('', '/v1/traces', '/v1/logs', '/v1/metrics')
        assert endpoint.port is not None and 1 <= endpoint.port <= 65535
        proxy_ports.add(endpoint.port)
assert len(proxy_ports) == 1
port = int(os.environ['DAGGER_SESSION_PORT'])
assert 1 <= port <= 65535
# This capability is generated for this local session, used only in memory,
# never printed or persisted in the numeric evidence.
header = 'Basic ' + base64.b64encode((os.environ['DAGGER_SESSION_TOKEN'] + ':').encode()).decode()
conn = http.client.HTTPConnection('127.0.0.1', port, timeout=240)
rows = []
observations = {}
deadline = time.monotonic() + 300
marker = workspace / 'marker.txt'
test = workspace / 'base_test.go'
originals = {f: f.read_bytes() for f in (marker, test)}

def rpc(label, query, variables=None, expected_error=None):
    assert len(rows) < 10
    remaining = deadline - time.monotonic()
    assert remaining > 0, '300-second total RPC budget exhausted'
    conn.timeout = remaining
    if conn.sock is not None:
        conn.sock.settimeout(remaining)
    row = {'index': len(rows), 'label': label, 'passed': False}
    rows.append(row)
    start = time.monotonic()
    conn.request('POST', '/query', json.dumps({'query': query, 'variables': variables or {}}),
                 {'Authorization': header, 'Content-Type': 'application/json'})
    response = conn.getresponse()
    raw = response.read(8 * 1024 * 1024 + 1)
    row['seconds'] = time.monotonic() - start
    row['http_status'] = response.status
    row['response_bytes'] = len(raw)
    assert len(raw) <= 8 * 1024 * 1024
    body = json.loads(raw)
    errors = body.get('errors') or []
    if response.status != 200 or errors:
        # Bounded raw response stays private; it can contain opaque object IDs.
        error_path = a.output.with_name(a.output.stem + '-rpc-' + str(row['index']) + '.private.json')
        fd = os.open(error_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as error_out:
            error_out.write(raw)
        row['private_error_response_saved'] = True
    assert response.status == 200
    row['graphql_error_count'] = len(errors)
    if expected_error:
        assert any(expected_error in e.get('message', '') for e in errors), 'expected edited-test failure absent'
    else:
        assert not errors, f'GraphQL failure in {label}; raw contents deliberately not logged'
    row['passed'] = True
    return body.get('data')

def retain_receiver(wid):
    data = rpc('retain-module', 'query($w:ID!){go{module(ws:$w,path:"."){id __typename tests(ws:$w){keys}}}}', {'w':wid})
    module = data['go']['module']
    typename = module['__typename']
    assert re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', typename)
    assert module['tests']['keys'] == ['TestBoundBase']
    return module['id'], typename

def consume_base(label, mid, typename, wid):
    query = 'query($m:ID!,$w:ID!){node(id:$m){... on ' + typename + '{base(ws:$w){id generation:envVariable(name:"ADDRESS_WITNESS_GENERATION") marker:envVariable(name:"ADDRESS_WITNESS_MARKER")}}}}'
    return rpc(label, query, {'m': mid, 'w': wid})['node']['base']

def service(label, ctr):
    data = rpc(label, 'query($c:ID!){node(id:$c){... on Container{withExec(args:["wget","-qO-","http://base-address-witness:8080/value"]){stdout}}}}', {'c': ctr['id']})
    assert data['node']['withExec']['stdout'] == ctr['generation'] + '\n' + ctr['marker']

def run_test(label, mid, typename, wid, fail=False):
    return rpc(label, 'query($m:ID!,$w:ID!){node(id:$m){... on ' + typename + '{test(ws:$w)}}}',
               {'m': mid, 'w': wid}, 'real-app-edit-sentinel' if fail else None)

status = 'incomplete'
try:
    wid = rpc('retain-workspace', '{currentWorkspace{id}}')['currentWorkspace']['id'] #1
    mid, typ = retain_receiver(wid) #2; explicit ws for module and tests
    addr = rpc('retain-address', 'query($w:ID!){node(id:$w){... on Workspace{resolve(value:"dag://base-witness/fresh"){id}}}}', {'w':wid})['node']['resolve']['id'] #3
    direct = []
    for n in range(2): #4,5
        direct.append(rpc('direct-never-' + str(n), 'query($a:ID!){node(id:$a){... on Address{container{generation:envVariable(name:"ADDRESS_WITNESS_GENERATION")}}}}', {'a': addr})['node']['container']['generation'])
    observations['direct_never_distinct'] = direct[0] != direct[1]
    assert observations['direct_never_distinct'], 'direct successful NEVER producer was reused'
    c1 = consume_base('retained-base-0', mid, typ, wid) #6
    c2 = consume_base('retained-base-1', mid, typ, wid) #7
    assert c1['generation'] and c2['generation']
    assert c1['marker'] == originals[marker].decode() == c2['marker']
    observations['retained_base_reaches_never_twice'] = c1['generation'] != c2['generation']
    observations['retained_base_same_container_id'] = c1['id'] == c2['id']
    service('service-from-first-base', c1) #8
    service('service-from-second-base', c2) #9
    run_test('actual-test-original', mid, typ, wid) #10
    status = 'passed-with-retained-cache-classification'
finally:
    for path, content in originals.items():
        path.write_bytes(content)
    conn.close()
    result = {'status': status, 'rpc_attempts': len(rows), 'rpc_cap': 10,
              'planned_rpc_calls': 10, 'session_count': 1, 'observations': observations,
              'rows': rows, 'restored': all(f.read_bytes() == b for f, b in originals.items()),
              'initial_file_sha256': {f.name: hashlib.sha256(b).hexdigest() for f,b in originals.items()},
              'private_error_responses_saved': sum(bool(r.get('private_error_response_saved')) for r in rows), 'tokens_saved': False, 'scope': 'correctness, not timing or normal CLI latency'}
    fd = os.open(a.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
