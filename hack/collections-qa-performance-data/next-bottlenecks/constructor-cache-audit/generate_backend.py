#!/usr/bin/env python3
"""Run normal Go SDK generation for only backend, restoring scope config afterward."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from prepare_measurement import CLI, ENGINE, OUT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('variant', choices=('control', 'constructor'))
    p.add_argument('--run', action='store_true')
    args = p.parse_args()
    command = [CLI, '--engine', 'container://' + ENGINE, '-y', 'generate', 'dagger-go-sdk/generate']
    if not args.run:
        print(json.dumps({'status': 'prepared only', 'variant': args.variant, 'command': command,
                          'temporary_change': 'select only backend SDK scope for generation; restore original dagger.toml unconditionally'}, indent=2))
        return
    app = OUT / args.variant / 'greetings-api'
    config = app / 'dagger.toml'
    original = config.read_bytes()
    start = original.index(b'[sdks.go.scopes.".dagger/modules/greetings"]')
    end = original.index(b'[sdks.typescript]', start)
    reduced = original[:start] + original[end:]
    assert b'[sdks.go.scopes.".dagger/modules/backend"]' in reduced
    output = OUT / 'generation' / args.variant
    output.mkdir(parents=True, exist_ok=False)
    (output / 'original-dagger.toml').write_bytes(original)
    (output / 'generation-dagger.toml').write_bytes(reduced)
    env = dict(os.environ)
    for key in ('DAGGER_CLOUD_URL', 'SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE',
                'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN'):
        env.pop(key, None)
    config.write_bytes(reduced)
    result = None
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=app, env=env, capture_output=True, timeout=900)
        (output / 'stdout.txt').write_bytes(result.stdout)
        (output / 'stderr.txt').write_bytes(result.stderr)
        print(result.stdout.decode(errors='replace'), end='')
        print(result.stderr.decode(errors='replace'), end='')
    finally:
        config.write_bytes(original)
        record = {'variant': args.variant, 'command': command,
                  'seconds_setup_only': time.monotonic() - started,
                  'exit_code': result.returncode if result is not None else None,
                  'original_config_restored': config.read_bytes() == original,
                  'original_config_sha256': hashlib.sha256(original).hexdigest(),
                  'reason_backend_scope_only': 'cache annotations affect backend runtime registration only; public backend signatures/defaultPath/ignore/up unchanged, so dependent greetings client signatures do not require regeneration'}
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        assert record['original_config_restored']
    assert result.returncode == 0, result.returncode


if __name__ == '__main__':
    main()
