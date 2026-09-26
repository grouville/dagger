from pathlib import Path
import hashlib, json, os, subprocess

lab = Path(__file__).resolve().parent
root = Path('/home/dagger/dag')
env = dict(os.environ, GOMAXPROCS='8', CGO_ENABLED='0', GOPROXY='off')
rows = []
for variant in ('baseline', 'candidate'):
    flags = ['-modfile=/tmp/collections-perf/post-rebase-io/build.mod', '-buildvcs=false']
    if variant == 'baseline':
        flags += ['-overlay=' + str(lab / 'baseline-overlay.json')]
    for kind in ('test', 'cli'):
        command = ['go', 'test', '-c', *flags, '-o', str(lab / (variant + '.test')), './internal/cmd/dagger'] if kind == 'test' else ['go', 'build', *flags, '-o', str(lab / ('dagger-' + variant)), './cmd/dagger']
        with (lab / (variant + '-' + kind + '-build.log')).open('wb') as log:
            subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        rows.append({'variant': variant, 'kind': kind, 'command': command})
    with (lab / (variant + '-tests.log')).open('wb') as log:
        subprocess.run([str(lab / (variant + '.test')), '-test.run=Test(ListedArtifact|ArtifactList|ArtifactCLI|ArtifactDimension|ArtifactKey|CommandArtifact|ListFormat)', '-test.v'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(variant + ' built and focused tests passed', flush=True)
files = ['artifact_list_baseline.go', 'baseline-overlay.json', 'baseline.test', 'candidate.test', 'dagger-baseline', 'dagger-candidate']
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()
provenance = {'root_revision': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(), 'commands':rows, 'sha256': {name:sha(lab/name) for name in files}, 'candidate_source_sha256':sha(root/'internal/cmd/dagger/artifact_list.go'), 'tests_source_sha256':sha(root/'internal/cmd/dagger/artifact_list_keys_test.go')}
(lab/'build-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
