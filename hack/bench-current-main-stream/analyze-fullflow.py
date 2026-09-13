#!/usr/bin/env python3
"""Complete-trace CLI invalidation analysis; cold/restart gates retained."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

OWNED = Path('/tmp/dagger-image-pipeline-source.MfcHBbgL')
BENCH = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop')
EXTRACTOR = BENCH / 'profile-command.py'
ANALYZER = Path('/tmp/dagger-rust-wcprof-otel')
CACHE_ANALYZER = OWNED / 'dagql-cache-analyzer'
CARGO = ['sh', '-c', 'rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked']
DPKG = ['sh', '-c', 'test "$(dpkg --print-architecture)" = amd64 && dpkg -i /tmp/rust-sync-libpopt.deb /tmp/rust-sync-rsync.deb']
RUSTUP = ['rustup', 'toolchain', 'install', '--no-self-update']
PROFILED = ('warmup-dagger', 'profile-library-repair', 'profile-exact', 'profile-application', 'profile-restart-exact', 'dependency-upgrade-dagger')
EXPECTED_RUST_LAYERS = {
    'sha256:039e6f9f9752f74a3ff4a6a224f64c7c864da16ed98f882107704328f41b9c42': 28232590,
    'sha256:167b9fde7ea2106ff0349f834ad13f3d5078836087edf8a9422da759c088f66c': 288641068,
}


def exact_rust_layer_bytes(progress):
    """Require the pinned full image once, including streamed download events."""
    for key in ('rust_unpack', 'rust_download'):
        rows = progress[key]
        if len(rows) != len(EXPECTED_RUST_LAYERS):
            return False
        actual = {row['item']: (row['current'], row['total']) for row in rows}
        if actual != {item: (size, size) for item, size in EXPECTED_RUST_LAYERS.items()}:
            return False
    return True


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def milliseconds(value):
    matched = re.fullmatch(r'([\d.]+)(ns|µs|ms|s)', value)
    if not matched:
        raise ValueError(value)
    return float(matched[1]) * {'ns': 1e-6, 'µs': .001, 'ms': 1, 's': 1000}[matched[2]]


def image_progress(spans, logs, process):
    groups = defaultdict(list)
    for row in logs:
        attrs = row.get('attrs', {})
        if attrs.get('dagger.io/progress.item'):
            groups[row['spanId'], attrs['dagger.io/progress.item']].append(row)
    result = []
    for (span_id, item), rows in groups.items():
        rows.sort(key=lambda row: row['timeNs'])
        first, last = rows[0], rows[-1]
        lineage, cursor = [], span_id
        while cursor in spans and cursor not in {entry['id'] for entry in lineage}:
            node = spans[cursor]
            lineage.append(dict(id=cursor, name=node['name']))
            cursor = node.get('parentId')
        transfer = next((entry['name'] for entry in lineage if entry['name'].startswith(('pulling ', 'preparing pull ', 'downloading image layer ', 'streaming image layer into private snapshot ', 'unpacking '))), '')
        if not transfer:
            continue
        attrs = last['attrs']
        current, total = int(attrs['dagger.io/progress.current']), int(attrs['dagger.io/progress.total'])
        nonzero = [row['timeNs'] for row in rows if int(row['attrs']['dagger.io/progress.current']) > 0]
        result.append(dict(span_id=span_id, item=item, transfer=transfer,
            first_ns=first['timeNs'], first_nonzero_ns=min(nonzero) if nonzero else None,
            last_ns=last['timeNs'], interval_ms=(last['timeNs'] - first['timeNs']) / 1e6,
            current=current, total=total, converged=total > 0 and current == total,
            explicit_empty_bodies=all('body' in row and row['body'] == '' for row in rows),
            before_process_exit=last['timeNs'] <= process['end_unix_ns'], records=len(rows)))
    rust_unpacks = [row for row in result if row['transfer'] == 'unpacking rust']
    rust_items = {row['item'] for row in rust_unpacks}
    rust_downloads = [row for row in result if row['item'] in rust_items and not row['transfer'].startswith('unpacking ')]
    layer_overlap = []
    for item in sorted(rust_items):
        reads = [row['first_nonzero_ns'] for row in rust_unpacks if row['item'] == item and row['first_nonzero_ns'] is not None]
        downloads = [row['last_ns'] for row in rust_downloads if row['item'] == item]
        layer_overlap.append(dict(item=item, first_read_ns=min(reads) if reads else None,
            download_end_ns=max(downloads) if downloads else None,
            read_before_own_download_end=bool(reads and downloads) and min(reads) < max(downloads)))
    return dict(all_transfers=result, rust_unpack=rust_unpacks, rust_download=rust_downloads,
        layer_overlap=layer_overlap,
        rust_download_bytes=sum(row['current'] for row in rust_downloads),
        rust_unpack_compressed_bytes=sum(row['current'] for row in rust_unpacks),
        observed_read_before_last_download=bool(rust_unpacks and rust_downloads) and
            min(row['first_nonzero_ns'] for row in rust_unpacks if row['first_nonzero_ns']) < max(row['last_ns'] for row in rust_downloads),
        note='Progress intervals bracket compressed reads, not exact Apply/commit CPU. Import envelope includes waiting in candidate. Network protocol/header/retry bytes are not measured by content progress.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    args = parser.parse_args()
    cohort = args.cohort.resolve(strict=True)
    assert cohort.parent == Path('/tmp') and cohort.name.startswith('dagger-rust-current-stream-ab-')
    meta = json.loads((cohort / 'cohort.json').read_text())
    raw = Path(meta['telemetry'])
    assert sha(ANALYZER) == 'de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba'
    assert CACHE_ANALYZER.exists(), 'Compile maintained standard-library-only cache analyzer outside timing slot'
    out = cohort / 'analysis-r2'
    out.mkdir(exist_ok=False)
    report = dict(cohort=str(cohort), metadata=meta, corpus_bytes=raw.stat().st_size,
        analyzer_sha256=sha(ANALYZER), extractor_sha256=sha(EXTRACTOR), cache_analyzer_sha256=sha(CACHE_ANALYZER),
        script_sha256=sha(__file__), profiles=[], rejected=[], caches=[], warm_rebuilds=[], all_captures_pass=False)
    for sample in meta['runs']:
        if 'root' not in sample:
            report['rejected'].append(dict(sample=sample, reason='No retained fixture root'))
            continue
        root = Path(sample['root'])
        fixture = json.loads((root / 'metadata.json').read_text())
        upgrade = fixture.get('dependency_upgrade', {})
        assert upgrade == {'package': 'bstr', 'from': '1.12.0', 'to': '1.13.0', 'transitions_per_run': 1,
                           'first': 'native' if (sample['index'] // 2) % 2 == 0 else 'dagger', 'profiled': True}
        assert fixture['cli_sha256'] == meta['cli_sha256'][sample['side']]
        assert fixture['engine_image_id'] == meta['image_ids'][sample['side']]
        assert fixture['samples'] == 3
        assert fixture['diagnostic_engine_config'] is None
        assert fixture['diagnostic_engine_config_sha256'] is None
        for failure_label in ('failure-probe', 'failure-revisit'):
            assert 'invalidation-probe' in (root / (failure_label + '.log')).read_text()
        for scenario, expected in (
            ('application', [('ripgrep', '15.2.0')]),
            ('workspace-library', [('grep', '0.4.1'), ('grep-printer', '0.3.1'), ('ripgrep', '15.2.0')])):
            for iteration in range(3):
                package_sets = {}
                for side, log_label in (('native', f'{scenario}-{iteration}-native'),
                                        ('dagger', f'{scenario}-{iteration}-cargo-diagnostic')):
                    log = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', (root / (log_label + '.log')).read_text())
                    package_sets[side] = sorted(set(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v([^\s]+)', log, re.MULTILINE)))
                record = dict(index=sample['index'], side=sample['side'], scenario=scenario, iteration=iteration,
                              packages=package_sets, passed=package_sets['native']==package_sets['dagger']==expected)
                report['warm_rebuilds'].append(record)
                if not record['passed']:
                    report['rejected'].append(dict(sample=sample, reason='Unexpected or unequal affected warm crates', rebuild=record))
        processes = [json.loads(line) for line in (root / 'processes.jsonl').read_text().splitlines()]
        failures = [row for row in processes if row['exit_code'] != (101 if row['label'] in ('failure-probe', 'failure-revisit') else 0)]
        if failures or sample.get('exit_code') != 0:
            report['rejected'].append(dict(sample=sample, reason='Unexpected process/cohort failure', failures=failures))
        for label in PROFILED:
            prefix = out / f'{sample["index"]}-{sample["side"]}-{label}'
            trace = Path(str(prefix) + '.trace.jsonl')
            extraction = subprocess.run([sys.executable, str(EXTRACTOR), '--processes', str(root / 'processes.jsonl'),
                '--otel', str(raw), '--label', label, '--output', str(trace)], text=True, capture_output=True)
            Path(str(prefix) + '.extraction.txt').write_text(extraction.stdout + extraction.stderr)
            if extraction.returncode:
                report['rejected'].append(dict(sample=sample, label=label, reason='Complete unique root extraction failed', error=extraction.stderr))
                continue
            extraction_info = json.loads(extraction.stdout)
            process = next(row for row in processes if row['label'] == label)
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            spans, logs = {}, []
            for row in rows:
                if row['kind'] == 'span':
                    old = spans.get(row['spanId'])
                    if old is None or row.get('endNs', 0) >= old.get('endNs', 0):
                        spans[row['spanId']] = row
                elif row['kind'] == 'log':
                    logs.append(row)
            analysis = subprocess.run([str(ANALYZER), '-top', '80', '-chain-depth', '40', str(trace)], text=True, capture_output=True)
            Path(str(prefix) + '.analysis.txt').write_text(analysis.stdout)
            Path(str(prefix) + '.gate.txt').write_text(analysis.stderr)
            markers = [span for span in spans.values() if span.get('attrs', {}).get('wcprof.session_complete')]
            declared = sum(int(span['attrs']['wcprof.session_span_count']) for span in markers)
            received = sum(bool(span.get('attrs', {}).get('wcprof.engine_span')) for span in spans.values())
            detail = dict(index=sample['index'], side=sample['side'], **extraction_info,
                declared_engine_spans=declared, received_engine_spans=received,
                structural_complete=analysis.returncode == 0 and 'structural gate: PASS' in analysis.stderr and bool(markers) and declared == received,
                execs=[], image_progress=image_progress(spans, logs, process))
            drift = re.search(r'drift vs actual: ([^)]+)', analysis.stdout)
            detail['replay_drift'] = drift[1] if drift else None
            detail['classes'] = []
            if 'top classes by total self-time\n' in analysis.stdout:
                table = analysis.stdout.split('top classes by total self-time\n', 1)[1].split('end-of-workload blocking chain', 1)[0]
                for line in table.splitlines():
                    matched = re.fullmatch(r'(.+?)\s+(engine|user)\s+(\d+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+.+', line)
                    if matched:
                        detail['classes'].append(dict(name=matched[1].strip(), count=int(matched[3]), self_ms=milliseconds(matched[4]), wall_ms=milliseconds(matched[5])))
            for span in spans.values():
                attrs = span.get('attrs', {})
                if span['name'] == 'exec.processRun' and attrs.get('wcprof.op.kind') == 'exec_phase':
                    parent = spans.get(span.get('parentId'), {})
                    exits = [event.get('attrs', {}).get('exit.code') for event in parent.get('events', []) if event['name'] == 'Container exited']
                    detail['execs'].append(dict(argv=json.loads(attrs['wcprof.exec.argv']), exit_codes=exits,
                        ms=(span['endNs'] - span['startNs']) / 1e6,
                        within_process=process['start_unix_ns'] <= span['startNs'] <= span['endNs'] <= process['end_unix_ns']))
            execs = detail['execs']
            if label == 'warmup-dagger':
                valid = sum(row['argv'] == CARGO for row in execs) == 1 and all(row['argv'] in (CARGO, DPKG, RUSTUP) for row in execs)
                valid = valid and len({tuple(row['argv']) for row in execs}) == len(execs)
            elif label in ('profile-exact', 'profile-restart-exact'):
                valid = not execs
            else:
                valid = len(execs) == 1 and execs[0]['argv'] == CARGO
            detail['expected_execs'] = valid and all(row['exit_codes'] == [0] and row['within_process'] for row in execs)
            detail['cargo_ms'] = sum(row['ms'] for row in execs if row['argv'] == CARGO)
            streams = defaultdict(str)
            for row in sorted(logs, key=lambda row: row['timeNs']):
                if row.get('scope') == 'dagger.io/engine.buildkit' and row.get('attrs', {}).get('stdio.stream') == 2:
                    streams[row['spanId']] += row.get('body', '')
            stderr = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', '\n'.join(streams.values()))
            detail['packages'] = sorted(set(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v([^\s]+)', stderr, re.MULTILINE)))
            native_label = ('warmup-native' if label == 'warmup-dagger' else
                            'dependency-upgrade-native' if label == 'dependency-upgrade-dagger' else None)
            detail['native_packages_equal'] = None
            if native_label:
                native = (root / (native_label + '.log')).read_text()
                native_packages = sorted(set(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v([^\s]+)', native, re.MULTILINE)))
                detail['native_packages_equal'] = native_packages == detail['packages']
            detail['dependency_packages_valid'] = True
            if label == 'warmup-dagger':
                detail['dependency_packages_valid'] = ('bstr', '1.12.0') in detail['packages'] and ('bstr', '1.13.0') not in detail['packages']
            elif label == 'dependency-upgrade-dagger':
                audited = json.loads((root / 'dependency-rebuilds.json').read_text())
                observed = [list(row) for row in detail['packages']]
                detail['dependency_packages_valid'] = (observed == audited['native'] == audited['dagger']
                    and ('bstr', '1.13.0') in detail['packages']
                    and all(name != 'memchr' and (name, version) != ('bstr', '1.12.0') for name, version in detail['packages'])
                    and not detail['image_progress']['all_transfers'])
            elif label == 'profile-application':
                # This diagnostic runs AFTER a failed library revisit and a
                # cache-hit repair. The immutable repair result does not rewind
                # the mutable Cargo/source cache left by the failed execution.
                # Keep this recovery case distinct from the ordinary timed
                # application loop above, which must rebuild only ripgrep.
                detail['profile_context'] = 'application edit after failure-revisit and cached repair, not the ordinary timed application loop'
                detail['dependency_packages_valid'] = detail['packages'] == [('grep', '0.4.1'), ('grep-printer', '0.3.1'), ('ripgrep', '15.2.0')]
            elif label == 'profile-library-repair':
                detail['dependency_packages_valid'] = detail['packages'] == [('grep', '0.4.1'), ('grep-printer', '0.3.1'), ('ripgrep', '15.2.0')]
            transfers = detail['image_progress']['rust_unpack'] + detail['image_progress']['rust_download']
            detail['progress_gates'] = all(row['converged'] and row['explicit_empty_bodies'] and row['before_process_exit'] for row in transfers)
            detail['cold_layer_evidence'] = label != 'warmup-dagger' or (bool(detail['image_progress']['rust_unpack']) and bool(detail['image_progress']['rust_download']))
            detail['exact_cold_layer_bytes'] = label != 'warmup-dagger' or exact_rust_layer_bytes(detail['image_progress'])
            detail['no_restart_image_transfer'] = label != 'profile-restart-exact' or not detail['image_progress']['all_transfers']
            detail['all_local_gates'] = all(detail[key] for key in ('structural_complete', 'expected_execs', 'progress_gates', 'cold_layer_evidence', 'exact_cold_layer_bytes', 'no_restart_image_transfer', 'dependency_packages_valid')) and detail['native_packages_equal'] is not False
            detail['image_spans'] = [dict(name=span['name'], start_ns=span['startNs'], end_ns=span['endNs'], ms=(span['endNs'] - span['startNs'])/1e6)
                for span in spans.values() if span.get('endNs', 0) and span['name'].startswith(('pulling ', 'preparing pull ', 'downloading image layer ', 'streaming image layer into private snapshot ', 'unpacking '))]
            rust_items = {entry['item'] for entry in detail['image_progress']['rust_unpack']}
            rust_spans = [span for span in detail['image_spans'] if span['name'] in ('pulling rust', 'preparing pull rust', 'unpacking rust') or any(span['name'] in ('downloading image layer ' + item, 'streaming image layer into private snapshot ' + item) for item in rust_items)]
            detail['rust_delivery_envelope_ms'] = (max(span['end_ns'] for span in rust_spans) - min(span['start_ns'] for span in rust_spans))/1e6 if rust_spans else None
            detail['root_children'] = [dict(name=span['name'], scope=span.get('scope'), ms=(span['endNs'] - span['startNs']) / 1e6)
                for span in spans.values() if span.get('endNs', 0) and span.get('parentId') in {root_span['spanId'] for root_span in spans.values() if root_span.get('scope') == 'dagger.io/cli' and not root_span.get('parentId')}]
            report['profiles'].append(detail)
            print(sample['side'], label, 'structural', detail['structural_complete'], 'exec', detail['expected_execs'], 'all', detail['all_local_gates'], flush=True)
        for name in ('first-check.wcprof.cache.json', 'application.wcprof.cache.json', 'restart-exact.wcprof.cache.json'):
            path = root / name
            if not path.exists():
                report['rejected'].append(dict(sample=sample, reason='Missing post-timer cache snapshot', name=name))
                continue
            cache = subprocess.run([str(CACHE_ANALYZER), '-top', '20', str(path)], text=True, capture_output=True)
            prefix = out / f'{sample["index"]}-{sample["side"]}-{name}'
            Path(str(prefix) + '.analysis.txt').write_text(cache.stdout + cache.stderr)
            report['caches'].append(dict(index=sample['index'], side=sample['side'], name=name, sha256=sha(path), bytes=path.stat().st_size, exit_code=cache.returncode))
    firsts = [row for row in report['profiles'] if row['label'] == 'warmup-dagger']
    report['cross_side_image_byte_sets_equal'] = len(firsts) == len(meta['runs']) and len({tuple(sorted((entry['item'], entry['current']) for entry in row['image_progress']['rust_download'])) for row in firsts}) == 1
    report['all_captures_pass'] = meta['status'] == 'passed' and not report['rejected'] and len(report['profiles']) == len(meta['runs']) * len(PROFILED) and all(row['all_local_gates'] for row in report['profiles']) and all(row['exit_code'] == 0 for row in report['caches']) and report['cross_side_image_byte_sets_equal']
    report['first_check_summary'] = {side: dict(samples=len(rows), medians={key: statistics.median(row[key] for row in rows) for key in ('process_ms', 'root_ms', 'before_root_ms', 'after_root_ms', 'cargo_ms')}) for side in ('A', 'B') if (rows := [row for row in firsts if row['side'] == side])}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(out / 'report.json'), all_captures_pass=report['all_captures_pass'], rejected=len(report['rejected']), first_check_summary=report['first_check_summary']), indent=2))


if __name__ == '__main__':
    main()
