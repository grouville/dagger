#!/usr/bin/env python3
"""Offline fixed-label/aggregate reduction; raw native wcprof stays private."""
from pathlib import Path
from collections import defaultdict
import hashlib, importlib.util, json

HERE = Path(__file__).resolve().parent
WARM = Path(__file__).resolve().parent / 'warm-reducer.py'
spec = importlib.util.spec_from_file_location('address_warm_reducer', WARM)
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)
EXTRA = (
    'session.serveQuery', 'session.loadWorkspace', 'session.loadModules',
    'session.buildSchema', 'session.query', 'moduleSource.loadContext',
    'moduleSource.loadSDK', 'ModuleSource.asModule', 'ModuleSource.runtime',
    'ModuleSource.generatedContextDirectory', 'ModuleSource.contextDirectory',
    'exec.setupNetwork', 'exec.setupRootfs', 'exec.runContainer',
    'exec.containerStart', 'exec.processRun', 'Container.from',
    'Container.withExec', 'Container.sync', 'GitRepository.tree',
)
ALLOWED = set(warm.LABELS) | set(EXTRA)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reduce(path, row):
    with path.open() as stream:
        head = json.loads(next(stream))
        events = [json.loads(line) for line in stream if line.strip()]
    operations = [event for event in events if event.get('e') == 'op']
    by_id = {op['id']: op for op in operations}
    def label(op): return head['strings'][op.get('c', 0)]
    epoch = head['epoch_unix_nano']
    groups = defaultdict(list)
    for op in operations:
        if label(op) in ALLOWED and op['k'] in warm.KINDS:
            groups[(label(op), op['k'])].append(op)
    classes = [{'class': name, 'kind': kind, **warm.stats(ops)}
               for (name, kind), ops in sorted(groups.items())]
    processes = []
    for op in sorted((op for op in operations if label(op) == 'exec.processRun'), key=lambda op: op['s']):
        argv = json.loads(head['strings'][op['m']]) if op.get('m') else []
        assert isinstance(argv, list)
        if len(argv) >= 2 and Path(argv[0]).name == 'go' and argv[1] == 'build':
            category = 'go-build'
        elif len(argv) >= 2 and Path(argv[0]).name == 'go' and argv[1] == 'mod':
            category = 'go-mod'
        else:
            category = 'other-process'
        chain, seen, parent = [], set(), by_id.get(op.get('p'))
        while parent:
            assert parent['id'] not in seen
            seen.add(parent['id'])
            if label(parent) in ALLOWED:
                chain.append({'class': label(parent), 'kind': parent['k'],
                              'duration_ms': (parent['d']-parent['s'])/1e6})
            parent = by_id.get(parent.get('p'))
        processes.append({'ordinal': len(processes), 'category': category,
                          'start_after_cli_ms': (epoch+op['s']-row['started_unix_ns'])/1e6,
                          'duration_ms': (op['d']-op['s'])/1e6,
                          'outcome': op.get('o'), 'allowed_parent_chain': chain})
    kinds = {}
    for category in ('go-build', 'go-mod', 'other-process'):
        selected = [op for op, value in zip(sorted((op for op in operations if label(op) == 'exec.processRun'), key=lambda op: op['s']), processes) if value['category'] == category]
        kinds[category] = warm.stats(selected)
    return {
        'variant': row['variant'], 'profile_sha256': sha(path),
        'instrumented_cli_seconds_not_ordinary': row['seconds'],
        'operations': len(operations), 'open_operations': len(head.get('open_ops', [])),
        'dropped_events': head.get('dropped_events', 0),
        'started_before_cli': sum(epoch+op['s'] < row['started_unix_ns'] for op in operations),
        'ended_after_cli': sum(epoch+op['d'] > row['exited_unix_ns'] for op in operations),
        'earliest_op_after_cli_ms': (epoch+min(op['s'] for op in operations)-row['started_unix_ns'])/1e6,
        'last_op_before_cli_exit_ms': (row['exited_unix_ns']-epoch-max(op['d'] for op in operations))/1e6,
        'fixed_classes': classes, 'process_groups': kinds, 'processes': processes,
        'scope': 'Process categories inspect private argv but publish only fixed labels. Inclusive sums and parent intervals overlap; no CPU attribution or additive savings claim.',
    }


def main():
    out = HERE / 'results-v1'
    rows = json.loads((out / 'results.json').read_text())
    assert len(rows) == 2 and all(row['correct'] and row['profile'] and not row['ordinary_sample'] for row in rows)
    profiles, warm_view = {}, {}
    for row in rows:
        path = out / f'{row["index"]}-{row["variant"]}' / 'run.wcprof.private'
        assert sha(path) == row['profile_sha256']
        profiles[row['variant']] = reduce(path, row)
        warm_view[row['variant']] = warm.reduce_profile(path)
    for name, value in [('phase-numeric.json', profiles), ('expansion-numeric.json', warm_view)]:
        (HERE / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({variant: {'operations': value['operations'], 'open': value['open_operations'],
                               'drops': value['dropped_events'], 'process_groups': value['process_groups']}
                      for variant, value in profiles.items()}, indent=2))


if __name__ == '__main__':
    main()
