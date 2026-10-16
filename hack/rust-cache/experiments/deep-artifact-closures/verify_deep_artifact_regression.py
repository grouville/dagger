from pathlib import Path
import json
import os
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'deep-artifact-regression'
root.mkdir(exist_ok=False)
module = Path('/tmp/dagger-rust-native-deep-artifact-closures/compiler')
before = {}
for name in ['history.go', 'batch.go']:
    path = root/('before-'+name)
    path.write_bytes(subprocess.check_output(['git', 'show', 'e63b6a2:compiler/replay/'+name], cwd=module))
    before[str(module/'replay'/name)] = str(path)
(root/'before-overlay.json').write_text(json.dumps({'Replace': before}, indent=2)+'\n')
original = (module/'replay/history.go').read_text()
needle = '\tif inputs.artifacts != nil {\n\t\tfor _, overlay := range overlays {'
assert original.count(needle) == 1
mutant = original.replace(needle, '\tif inputs.artifacts != nil && len(missingOutputs) > 0 {\n\t\tfor _, overlay := range overlays {')
(root/'mutant-history.go').write_text(mutant)
(root/'mutant-overlay.json').write_text(json.dumps({'Replace': {str(module/'replay/history.go'): str(root/'mutant-history.go')}}, indent=2)+'\n')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://172.17.0.16:43184')
results = []
for label in ['before', 'mutant']:
    command = ['python3', str(base/'local_cli_collector.py'), 'api', 'with-session', '--',
               '/home/dagger/.local/bin/go', 'test', '-tags=integration', '-overlay='+str(root/(label+'-overlay.json')),
               '-count=1', '-run', '^TestBatchHistoryRestoresRevertedArtifacts$', '-v', './replay']
    with (root/(label+'.log')).open('w') as output:
        result = subprocess.run(command, cwd=module, env=env, stdout=output, stderr=subprocess.STDOUT)
    text = (root/(label+'.log')).read_text()
    if label == 'before':
        assert result.returncode == 0, label
    else:
        assert result.returncode != 0 and 'binary output =' in text and 'want "2"' in text, text[-3000:]
    results.append(dict(label=label, returncode=result.returncode, expected=True))
    (root/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    print('PASS', label, 'matches expected outcome', result.returncode, flush=True)
