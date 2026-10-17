from pathlib import Path
import collections
import json
import subprocess

root = Path(__file__).parent
summaries = {}
for arm in ['original', 'candidate']:
    path = root / arm
    with (path / 'wcprof-complete.ndjson').open() as stream:
        header = json.loads(next(stream))
        strings = header['strings']
        ops = {}
        for line in stream:
            event = json.loads(line)
            if event['e'] == 'op':
                ops[event['id']] = event
    children = collections.defaultdict(list)
    for op in ops.values():
        children[op.get('p', 0)].append(op)
    def cls(op):
        return strings[op['c']]
    def seconds(op):
        return (op['d'] - op['s']) / 1e9
    records = []
    for call in ops.values():
        if call['k'] != 'call' or not cls(call).endswith('.ownFiles'):
            continue
        pending = [call]
        functions = []
        while pending:
            parent = pending.pop()
            for child in children[parent['id']]:
                if cls(child) == 'dang.evaluateFunction':
                    functions.append(child)
                elif child['k'] not in ['call', 'session_phase']:
                    pending.append(child)
        for fn in functions:
            api = [op for op in children[fn['id']] if cls(op) == 'dang.apiRequest']
            records.append(dict(call_id=call['id'], function_id=fn['id'],
                call_seconds=seconds(call), function_seconds=seconds(fn),
                direct_api_requests=len(api), api_seconds=sum(map(seconds, api))))
    records.sort(key=lambda row: row['call_seconds'], reverse=True)
    queries = sorted((op for op in ops.values() if cls(op) == 'session.serveQuery'),
        key=seconds, reverse=True)
    summary = dict(ownfiles_executions=len(records),
        ownfiles_direct_api_requests=sum(r['direct_api_requests'] for r in records),
        ownfiles=records, largest_queries=[dict(id=op['id'], seconds=seconds(op)) for op in queries[:5]])
    (path / 'discovery-structure.json').write_text(json.dumps(summary, indent=2)+'\n')
    for label, opid in [('main', queries[0]['id']), ('ownfiles', records[0]['call_id'])]:
        args = ['/tmp/rust-cache-wcprof-report', '-view', 'critpath', '-op', str(opid),
            str(path / 'wcprof-complete.ndjson')]
        with (path / f'{label}-critical.txt').open('w') as out:
            subprocess.run(args, stdout=out, stderr=subprocess.STDOUT, check=True)
    summaries[arm] = summary
    print(arm, 'executions', len(records), 'direct API requests', summary['ownfiles_direct_api_requests'],
        'largest', records[0], flush=True)
(root / 'discovery-comparison.json').write_text(json.dumps(summaries, indent=2)+'\n')
