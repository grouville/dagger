import os
import subprocess
import sys
from pathlib import Path

collector = Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
runner = os.environ.get('RUST_CACHE_BENCH_RUNNER', 'tcp://127.0.0.1:16247')
env.update(DAGGER_CLOUD_URL=os.environ.get('RUST_CACHE_BENCH_COLLECTOR', 'http://' + collector + ':43183'), DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST=runner)
cli = os.environ.get('RUST_CACHE_BENCH_CLI', '/tmp/native-hash-verification-bin/dagger')
raise SystemExit(subprocess.call([cli, *sys.argv[1:]], env=env))
