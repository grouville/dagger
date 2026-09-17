#!/usr/bin/env python3
"""Record and stop one receipt-validated owned runtime; never remove its data."""
import argparse
import importlib.util
import json
import subprocess
import time

import build
from profile_import import GUARD, PINS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', type=int, choices=range(1, 129))
    args = parser.parse_args()
    runtime = build.ROOT / ('runtime' if args.attempt == 1 else f'runtime-r{args.attempt}')
    out = runtime / 'stopped.json'
    assert not out.exists()
    env = build.environment()
    image = json.loads((runtime / 'image.json').read_text())
    owner = json.loads((runtime / 'owner.json').read_text())
    name = f'dagger-storage-host-efb1uyhh-r{args.attempt}-engine'
    assert build.sha(GUARD) == PINS[GUARD]
    spec = importlib.util.spec_from_file_location('owned_runtime_guard', GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    def selected(kind, fields):
        template = '{' + ','.join(json.dumps(k) + ':{{json .' + k + '}}' for k in fields) + '}'
        return json.loads(build.read(['docker', kind, 'inspect', name, '--format', template], env))
    fields = ('Id', 'Name', 'Image', 'Mounts', 'State.Running', 'State.Pid', 'State.StartedAt', 'RestartCount')
    row = selected('container', fields)
    owned = guard.engine(row, name, image['id'], runtime / 'cli/config/dagger/engine.json', owner['engine'])
    guard.volume(selected('volume', ('Name', 'Driver', 'Mountpoint', 'CreatedAt', 'Scope', 'Options', 'Labels')),
                 owned, owner['volume'])
    assert row['State.Running']
    subprocess.run(['docker', 'stop', '--time=30', owned['id']], env=env, capture_output=True, check=True, timeout=60)
    stopped_ns = time.time_ns()
    stopped = selected('container', fields)
    assert not stopped['State.Running'] and stopped['Id'] == owned['id']
    assert stopped['Image'] == image['id'] and stopped['RestartCount'] == owned['restart_count']
    with (runtime / 'engine-complete.log').open('xb') as log:
        subprocess.run(['docker', 'logs', owned['id']], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=30)
    out.write_text(json.dumps(dict(owner=owner, stopped=stopped, stopped_ns=stopped_ns, controller_sha256=build.sha(__file__),
                                   data_removed=False), indent=2) + '\n')
    print(json.dumps({'attempt': args.attempt, 'stopped': True, 'data_removed': False}), flush=True)


if __name__ == '__main__':
    main()
