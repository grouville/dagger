"""Publish only fixed classes, public alias allowlist, counts and relative times."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json

H = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
PUBLIC_ALIASES = frozenset(('backend', 'frontend', 'greetings', 'go', 'gomod', 'eslint', 'golangci-lint', 'playwright', 'dagger-go-sdk', 'dagger-typescript-sdk'))
DANG = ('dang.runtimeCall', 'dang.runtimeSchemaFile', 'dang.nestedTransportRegister', 'dang.nestedListener', 'dang.schemaLoad', 'dang.schemaOpen', 'dang.decodeSchema', 'dang.cloneSchema', 'dang.sourceMount', 'dang.runSource', 'dang.selfTypes', 'dang.objectDirectives', 'dang.invoke', 'dang.flushTelemetry')
PUBLIC_CALLS = frozenset(('go:Query.go', 'go:Go.modules', 'go:GoModules.get', 'go:GoModule.tests', 'go:GoModule.base', 'gomod:Query.gomod', 'gomod:Gomod.modules', 'gomod:Gomod.workspaceRootPath', 'gomod:GomodGoMod.ownFiles', 'gomod:Gomod.normalizeDirectoryPath', 'gomod:Gomod.normalizeFilePath', 'backend:Query.backend', 'backend:Backend.goTestBase'))
FIXED = DANG + ('Workspace.artifacts', 'Artifacts.__itemsJSON', 'artifact.moduleTree', 'artifact.coreTree', 'workspace.moduleLoad', 'session.query', 'Address.container', 'Query.typeDef', 'TypeDef.withOptional', 'Query.__schemaJSONFile', 'schema.forkPrepared') + tuple(sorted(PUBLIC_CALLS))


def union_ns(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def stats(ops):
    return {'count': len(ops), 'inclusive_sum_ms': sum(o['d'] - o['s'] for o in ops) / 1e6, 'union_ms': union_ns([(o['s'], o['d']) for o in ops]) / 1e6, 'max_ms': max((o['d'] - o['s'] for o in ops), default=0) / 1e6}


def subtract(intervals, mask):
    """Interval remainder, not inferred CPU or critical-path work."""
    output = []
    for start, end in intervals:
        cursor = start
        for lo, hi in sorted(mask):
            if lo >= end:
                break
            if hi <= cursor:
                continue
            if lo > cursor:
                output.append((cursor, min(lo, end)))
            cursor = max(cursor, hi)
        if cursor < end:
            output.append((cursor, end))
    return output


def analyze(path, expected_hash):
    assert sha(path) == expected_hash
    with path.open() as stream:
        header = json.loads(next(stream))
        ops = [row for line in stream if line.strip() for row in [json.loads(line)] if row.get('e') == 'op']
    strings = header['strings']
    names = lambda o: strings[o.get('c', 0)]
    by_id = {o['id']: o for o in ops}
    children = defaultdict(list)
    for o in ops:
        children[o.get('p')].append(o)

    def descendants(op):
        seen = set()
        todo = list(children[op['id']])
        result = []
        while todo:
            child = todo.pop()
            if child['id'] in seen:
                continue
            seen.add(child['id'])
            result.append(child)
            todo.extend(children[child['id']])
        return result

    def owner(op):
        seen = set()
        current = by_id.get(op.get('p'))
        while current and current['id'] not in seen:
            seen.add(current['id'])
            if current['k'] == 'call_exec':
                return current
            current = by_id.get(current.get('p'))
        return None

    catalog = [o for o in ops if names(o) == 'Workspace.artifacts' and o['k'] == 'call_exec']
    expanded = [o for o in ops if names(o) == 'Artifacts.__itemsJSON' and o['k'] == 'call_exec']
    anchor = min((o['s'] for o in catalog), default=min(o['s'] for o in ops))
    phases = []
    for name in FIXED:
        for kind in sorted({o['k'] for o in ops if names(o) == name}):
            phases.append({'class': name, 'kind': kind, **stats([o for o in ops if names(o) == name and o['k'] == kind])})

    runtime_calls = []
    for ordinal, call in enumerate(sorted([o for o in ops if names(o) == 'dang.runtimeCall'], key=lambda o: o['s'])):
        parent = owner(call)
        parent_name = names(parent) if parent else None
        nested = descendants(call)
        rows = []
        for name in DANG[1:]:
            matches = sorted([o for o in nested if names(o) == name], key=lambda o: o['s'])
            for index, child in enumerate(matches):
                rows.append({'class': name, 'ordinal_within_class': index, 'start_after_runtime_ms': (child['s'] - call['s']) / 1e6, 'duration_ms': (child['d'] - child['s']) / 1e6})
        runtime_calls.append({'ordinal': ordinal, 'owner_class': parent_name if parent_name in PUBLIC_CALLS else 'other', 'duration_ms': (call['d'] - call['s']) / 1e6, 'start_after_owner_ms': (call['s'] - parent['s']) / 1e6 if parent else None, 'phases': rows})

    loads = sorted([o for o in ops if names(o) == 'workspace.moduleLoad'], key=lambda o: o['s'])
    readiness = []
    for ordinal, load in enumerate(loads):
        alias = strings[load.get('i', 0)]
        readiness.append({'ordinal': ordinal, 'alias': alias if alias in PUBLIC_ALIASES else 'other', 'start_after_catalog_ms': (load['s'] - anchor) / 1e6, 'ready_after_catalog_ms': (load['d'] - anchor) / 1e6, 'duration_ms': (load['d'] - load['s']) / 1e6})
    windows = []
    for name, seq in [('catalog', catalog), ('expansion', expanded)]:
        for index, op in enumerate(sorted(seq, key=lambda o: o['s'])):
            windows.append({'phase': name, 'ordinal': index, 'start_after_catalog_ms': (op['s'] - anchor) / 1e6, 'end_after_catalog_ms': (op['d'] - anchor) / 1e6, 'duration_ms': (op['d'] - op['s']) / 1e6})
    expansion_scopes = []
    for expansion in sorted(expanded, key=lambda o: o['s']):
        inside = [o for o in ops if o['s'] >= expansion['s'] and o['d'] <= expansion['d']]
        phase_rows = []
        for name in DANG + ('Query.__schemaJSONFile', 'schema.forkPrepared'):
            matches = [o for o in inside if names(o) == name]
            if not matches:
                continue
            remainder = []
            for op in matches:
                child_intervals = [(max(op['s'], c['s']), min(op['d'], c['d'])) for c in children[op['id']] if c['s'] < op['d'] and c['d'] > op['s']]
                remainder.extend(subtract([(op['s'], op['d'])], child_intervals))
            phase_rows.append({'class': name, **stats(matches), 'hits': sum(o.get('o') == 'hit' for o in matches), 'without_direct_profile_children_union_ms': union_ns(remainder) / 1e6})
        intervals = lambda name: [(o['s'], o['d']) for o in inside if names(o) == name]
        invokes = intervals('dang.invoke')
        flushes = intervals('dang.flushTelemetry')
        sources = intervals('dang.runSource')
        direct_kinds = defaultdict(int)
        nested_runtime_descendants = 0
        for op in inside:
            if names(op) != 'dang.invoke':
                continue
            nested_runtime_descendants += sum(names(child) == 'dang.runtimeCall' for child in descendants(op))
            for child in children[op['id']]:
                label = names(child)
                direct_kinds[label if label in DANG else 'other'] += 1
        expansion_scopes.append({'duration_ms': (expansion['d'] - expansion['s']) / 1e6, 'phases': phase_rows, 'invoke_union_without_any_active_flush_ms': union_ns(subtract(invokes, flushes)) / 1e6, 'source_union_outside_every_invoke_ms': union_ns(subtract(sources, invokes)) / 1e6, 'invoke_union_outside_every_source_ms': union_ns(subtract(invokes, sources)) / 1e6, 'invoke_direct_child_classes': dict(direct_kinds), 'invoke_parent_linked_runtime_descendants': nested_runtime_descendants, 'caveat': 'Parent-child remainder is unrecorded wall time, not exclusive CPU. Nested GraphQL request execution can be represented under separate request roots; interval unions expose overlap without asserting absent work.'})
    go = [o for o in loads if strings[o.get('i', 0)] == 'go']
    remaining = None
    if go and loads:
        last_go = max(o['d'] for o in go)
        remaining = {'go_last_ready_after_catalog_ms': (last_go - anchor) / 1e6, 'last_any_load_after_catalog_ms': (max(o['d'] for o in loads) - anchor) / 1e6, 'gap_ms': (max(o['d'] for o in loads) - last_go) / 1e6, 'interpretation': 'Resolution-end gap across recorded loads, not proven removable critical-path time; publication still occurs after each unchanged batch.'}
    return {'profile_sha256': expected_hash, 'operations': len(ops), 'open_operations': len(header.get('open_ops', [])), 'dropped_events': header.get('dropped_events', 0), 'phases': phases, 'runtime_calls': runtime_calls, 'workspace_module_readiness': readiness, 'catalog_and_expansion': windows, 'expansion_scopes': expansion_scopes, 'go_readiness_gap': remaining, 'unknown_alias_occurrences': sum(r['alias'] == 'other' for r in readiness)}


def main():
    rows = json.loads((H / 'results-v1/results.json').read_text())
    assert len(rows) == 4 and all(row['correct'] for row in rows)
    result = {'reducer_sha256': sha(__file__), 'profiles': [], 'caveats': ['Two separately profiled unchanged calls; no A/B speedup claim.', 'Inclusive durations and nested or parallel intervals overlap; do not add phase sums.', 'Runtime ownership here means nearest enclosing call_exec, not a public cache or permission scope.', 'Module-ready timestamps measure resolution completion; publication and dependency compatibility remain required.', 'Raw wcprof IDs, arbitrary aliases, string tables and payloads remain private.']}
    for row in rows:
        if row['profile']:
            profile = H / 'results-v1' / ('%02d-%s' % (row['index'], row['label'])) / 'run.wcprof.private'
            result['profiles'].append(analyze(profile, row['profile_sha256']))
    assert len(result['profiles']) == 2
    (H / 'numeric-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'profiles': len(result['profiles']), 'readiness': [p['go_readiness_gap'] for p in result['profiles']], 'runtime_calls': [len(p['runtime_calls']) for p in result['profiles']]}))


if __name__ == '__main__':
    main()
