#!/usr/bin/env python3
"""Run the unchanged profile controller with explicit client diagnostics.

The controller keeps all native/source/identity gates. The wrapper records its
own provenance and validates the independent sender-counter output afterward.
"""
import json
from pathlib import Path
import re
import sys

import build
import profile_import

ROOT = build.ROOT


def main():
    label = sys.argv[1]
    attempt = int(sys.argv[sys.argv.index('--attempt') + 1])
    runtime = ROOT / f'runtime-r{attempt}'
    original_environment = build.environment

    def diagnostic_environment():
        env = original_environment()
        # Deliberately after the ordinary controller scrubs ambient overrides.
        env['_DAGGER_FILESYNC_PHASE_PROFILE'] = '1'
        return env

    build.environment = diagnostic_environment
    profile_import.main()
    path = runtime / label / 'receipt.json'
    record = json.loads(path.read_text())
    assert record['status'] == 'source-and-profile-validated-diagnostic-only'
    records = []
    stderr = (runtime / label / 'stderr').read_text()
    for line in stderr.splitlines():
        line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line)
        start = line.find('{"kind":"filesync.client.walk"')
        if start < 0:
            continue
        value, _ = json.JSONDecoder().raw_decode(line[start:])
        assert not value['failed']
        keys = ('enumerate_filter_ns', 'entry_info_ns', 'packet_bookkeeping_ns', 'stat_send_ns')
        assert all(value[key] >= 0 for key in keys)
        assert sum(value[key] for key in keys) == value['walk_ns']
        records.append(value)
    assert records and max(value['entries'] for value in records) >= 12025, 'missing Ruff sender diagnostic'
    record['phase_diagnostics'] = {
        'wrapper_sha256': build.sha(__file__),
        'cli_environment': {'_DAGGER_FILESYNC_PHASE_PROFILE': '1'},
        'client_walks': records,
        'stderr_sha256': build.sha(runtime / label / 'stderr'),
        'status': 'client-partitions-validated',
    }
    path.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
