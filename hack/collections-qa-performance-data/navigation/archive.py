"""Explicit public evidence allowlist. Never copy raw output, logs or wcprof."""
from pathlib import Path
import hashlib
import json

LAB = Path(__file__).resolve().parent
REPO = Path('/home/dagger/dag')
OUT = REPO / 'hack/collections-qa-performance-data/navigation'
CLI = Path('/tmp/collections-perf/cli-exit-tail-v2')
AUDIT = Path('/tmp/collections-perf/warm-audit')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


files = {}


def add(source, relative):
    source = Path(source)
    assert source.is_file(), source
    assert not str(source).endswith(('.wcprof', '.log'))
    assert source.name not in ('stdout.txt', 'stderr.txt')
    assert relative not in files
    files[relative] = source


for directory, prefix in (
    ('exit-tail-diagnostic-v1', 'exit'),
    ('navigation-generate-v1', 'navigation'),
    ('cold-navigation-v1', 'cold'),
    ('cold-navigation-profile-v1', 'cold-profile'),
):
    for name in ('driver.py.txt', 'results.json', 'summary.json', 'provenance.json'):
        add(LAB / directory / name, prefix + '/' + name)
    for name in ('fixture-validation.json', 'restoration.json', 'setup.json'):
        if (LAB / directory / name).is_file():
            add(LAB / directory / name, prefix + '/' + name)
add(LAB / 'derive-exit-tail.py', 'exit/derive.py')
add(LAB / 'exit-tail-evidence-v1/analysis.json', 'exit/analysis.json')
for name in ('analysis.json', 'derive.py', 'report.md'):
    add(LAB / 'navigation-evidence-v1' / name, 'navigation/' + name)
add(LAB / 'cold-navigation-evidence-v1/analysis.json', 'cold/analysis.json')
for name in ('experiment.py', 'withfile-cloud-warm.py', 'navigation-generate.py'):
    add(LAB / name, 'drivers/' + name)
for name in ('README.md', 'PRIVACY-AND-CONCURRENCY-REVIEW.md', 'prerun-spike-source-audit.md',
             'source-manifest.json', 'build-results.json', 'build.mod', 'build.sum',
             'overlay.json', 'diagnostic.patch', 'prepare.py', 'build.py'):
    add(CLI / name, 'cli/' + name)
for name in ('perf_exit_diagnostic.go', 'cli_main.go', 'cli_engine.go', 'engine_client.go',
             'otel_init.go', 'analytics.go', 'cloud_export_sequence.go'):
    add(CLI / 'source' / name, 'cli/source/' + name + '.txt')
for name in ('report.md', 'numeric-phases.json', 'summary.json'):
    add(AUDIT / 'exit-tail-audit/shutdown-log-evidence' / name, 'shutdown/' + name)
for name in ('report.md', 'numeric.json', 'analyze.py'):
    add(AUDIT / 'list-all-current' / name, 'discovery/' + name)
for name in ('validation.json', 'manifest.json', 'source.patch'):
    add(AUDIT / 'exit-tail-audit/metrics-final-collection' / name, 'metrics/' + name)
add(AUDIT / 'exit-tail-audit/report.md', 'shutdown/ownership-review.md')
add(Path(__file__), 'archive.py')

assert not OUT.exists(), 'do not overwrite a published evidence set'
manifest = []
for relative, source in sorted(files.items()):
    dest = OUT / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source.read_bytes())
    manifest.append({'path': relative, 'sha256': sha(dest), 'bytes': dest.stat().st_size})
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(OUT / 'README.md').write_text('''# Navigation and command-completion evidence

See [the report](../../collections-navigation-performance.md) for interpretation.
The archive covers 55 validated commands: 46 ordinary-production-Cloud calls and
nine local setup/correctness calls. Instrumented calls are kept separate from
ordinary latency medians. Native generation is not SDK code generation.

Only explicitly selected numeric reports, source/fixture hashes, driver code and
diagnostic source are included. Raw stdout/stderr, engine logs, wcprof files,
credentials and private API code are excluded. Source paths describe the original
benchmark machine; use the recorded pins/hashes to reconstruct the experiment.

The metric fix is independently validated by real SDK reader and lifecycle tests.
These command timings use the preceding engine binaries and do not establish a
latency improvement from that fix. Cold means a new Dagger volume with an already
available image, and excludes engine provisioning/readiness. The target remains
500 ms for complete commands.
''')
print(json.dumps({'selected_files': len(files), 'bytes': sum(row['bytes'] for row in manifest)}))
