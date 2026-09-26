"""Explicit allowlist: never copy raw traces, Cloud output, credentials or API code."""
from pathlib import Path
import hashlib,json,shutil
lab=Path(__file__).resolve().parent
sdk=Path('/tmp/collections-perf/sdk-edit-audit')
repo=Path('/home/dagger/dag');dest=repo/'hack/collections-qa-performance-data/lazy-source'
dest.mkdir(exist_ok=True)
files={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def add(source,name):
    source=Path(source);target=dest/name
    assert source.is_file(),source
    assert target.suffix not in ('.go','.wcprof','.pprof')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    files[name]={'sha256':sha(target),'source':str(source),'source_sha256':sha(source)}
allow=json.loads((lab/'evidence-skeleton/archive-allowlist.json').read_text())
for name in allow['files']:
    if name.endswith('report-skeleton.md'):continue
    source=lab/name;assert sha(source)==allow['sha256'][name]
    add(source,'matrix/'+source.name)
for name in ('experiment.py','profile-edits.py','build.py','builds.json','build-withfile.py','build-withfile.json','derive-withfile.py','withfile-http-pairs.py','withfile-cloud.py','withfile-followup.py'):
    add(lab/name,'drivers/'+name)
add(lab/'withfile-v1/driver.py.txt','drivers/withfile-pairs.py.txt')
for name in ('local-samples.json','local-summary.json','paired-deltas.json','profile-proof.json','correctness.json','restoration.json','build.json','provenance.json','cloud-samples.json','cloud-summary.json','cloud-restoration.json','cloud-provenance.json'):
    add(lab/'withfile-evidence'/name,'withfile/'+name)
for name in ('followup-provenance.json','unaccepted-negative-control.json'):
    add(lab/'withfile-v1'/name,'withfile/'+name)
for name in ('harness-correction.json','driver.py.txt','corrected-driver.py.txt'):
    add(lab/'withfile-cloud-v1'/name,'withfile/cloud-'+name)
warm=json.loads((lab/'withfile-evidence/cloud-warm-allowlist.json').read_text())
for name in ('cloud-warm-report.md','cloud-warm-analysis.json'):
    expected=next(r['sha256'] for r in warm['allowed_files'] if r['name']==name)
    assert sha(lab/'withfile-evidence'/name)==expected
    add(lab/'withfile-evidence'/name,'withfile/'+name)
add(lab/'withfile-cloud-warm.py','drivers/withfile-cloud-warm.py')
for name in ('results.json','summary.json','provenance.json','fixture-validation.json','attempts.json'):
    add(lab/'withfile-cloud-warm-v1'/name,'withfile/cloud-warm-'+name)
http=json.loads((lab/'withfile-evidence/http-archive-allowlist.json').read_text())
# Exact names are listed here as well so a changed external allowlist cannot
# silently broaden the publication boundary.
for name in ('http-samples.json','http-summary.json','http-profile-proof.json','http-verification.json','http-restoration.json','http-report.md','http-derive.py'):
    source=lab/'withfile-evidence'/name
    assert sha(source)==http['sha256']['withfile-evidence/'+name]
    add(source,'withfile/'+name)
for name in ('manifest.json','base-overlay.json','interface-overlay.json','combined-overlay.json','build.mod','build.sum','upstreamability.md'):
    add(sdk/'metadata-build-v1'/name,'build/'+name)
for name in ('source.patch','manifest.json','engine-overlay.json'):
    add(sdk/'withfile-source-lazy'/name,'build/withfile-'+name)
add(sdk/'withfile-source-lazy/container_source_lazy_test.go','validation/privileged-copy-test.go.txt')
for name in ('unit-privileged.json','unit-privileged.log','race-privileged.json','race-privileged.log'):
    add(sdk/'withfile-source-lazy'/name,'validation/'+name)
for folder in ('interface-signatures','dang-clone-leaves'):
    add(sdk/folder/'prototype.patch','prototypes/'+folder+'.patch')
add('/tmp/collections-perf/warm-audit/public-pr-overlap-refresh.md','public-pr-overlap.md')
validation=sdk/'withfile-source-lazy/upstream-v1/applied-validation-v2'
assert json.loads((validation/'results.json').read_text())['status']=='passed'
add(validation/'results.json','validation/applied-results.json')
add(validation/'summary.json','validation/applied-summary.json')
add(validation.parent/'applied-validation-v1/results.json','validation/rejected-fixture-attempt.json')
add(sdk/'withfile-source-lazy/upstream-v1/validate-applied.py','validation/validate-applied.py')
add(sdk/'withfile-source-lazy/upstream-v1/applied-validation-inputs.json','validation/applied-inputs.json')
add(sdk/'withfile-source-lazy/upstream-v1/REVIEW.md','validation/portable-test-review.md')
add(Path(__file__),'archive.py')
(dest/'manifest.json').write_text(json.dumps({'policy':__doc__,'files':files},indent=2)+'\n')
print(json.dumps({'files':len(files),'bytes':sum((dest/n).stat().st_size for n in files)}))
