from pathlib import Path
import gzip,hashlib,json,shutil,subprocess,tarfile
base=Path('/tmp/rust-cache-sipsma-review')
source=base/'plan-decode-libraries'
root=Path('hack/rust-cache/experiments/plan-decoder')
root.mkdir(exist_ok=False)
def copy(path,relative):
    destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy(path,destination)
def compress(path,relative):
    destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:output.write(Path(path).read_bytes())
for name in ['library-versions.json','compiler-tool-identities.json','derived-statistics.json','go.mod','go.sum']:
    copy(source/name,name)
for name in ['main.go','model/model.go']:
    compress(source/name,'benchmark-source/'+name+'.gz')
for name in ['metadata.json','samples.json','summary.json','source-hashes.json','admission.jsonl']:
    if (source/'first-use'/name).exists():copy(source/'first-use'/name,'first-use/'+name)
with tarfile.open(root/'first-use/raw-logs.tar.gz','w:gz') as output:
    for p in sorted((source/'first-use').glob('*.log')):output.add(p,arcname=p.name)
compress(source/'first-use-driver.log','first-use/driver.log.gz')
for cohort in ['paired','crossover']:
    directory=base/('plan-decoder-'+cohort)
    for name in ['metadata.json','summary.json','samples.json','pressure.jsonl','admission.jsonl']:
        copy(directory/name,cohort+'/'+name)
    compress(source/(cohort+'-driver.log'),cohort+'/driver.log.gz')
    with tarfile.open(root/(cohort+'/command-logs.tar.gz'),'w:gz') as output:
        for p in sorted(directory.glob('*.log')):output.add(p,arcname=p.name)
profiles=base/'plan-decoder-command-profiles'
for p in sorted(profiles.iterdir()):
    if p.suffix in ['.log','.ndjson']:compress(p,'profiles/'+p.name+'.gz')
    else:copy(p,'profiles/'+p.name)
for name in ['module-race.log','module-race-compatible.log','decoder-race.log','decoder-fuzz.log','module-dependency.log','dependencies.log','build.log','build-compatible.log','workers-before-build.log','workers-after-build.log','native-validation.log','final-reuse.log','stall-profile-driver.log']:
    compress(source/name,'validation/'+name+'.gz')
copy(base/'plan-decoder-validation/results.json','validation/native-cold-edit-results.json')
for size in ['130','1026','small']:
    compress(base/'deep-artifact-reuse-usage-maps-post-restart'/(size+'-before.cache.json.plan.json'),'plans/'+size+'.json.gz')
for name in ['prepare_plan_decode_benchmark.py','measure_plan_decode_libraries.py','measure_native_plan_decoder.py','profile_native_command_stalls.py','verify_native_plan_decoder.py','check_native_plan_decoder_reuse.py','summarize_plan_decoder_work.py','archive_plan_decoder_work.py']:
    copy(base/name,name)
compress(source/'source.patch','source.patch.gz')
for name in ['compiler/replay/plan_decode.go','compiler/replay/plan_decode_test.go']:
    compress(Path('/tmp/dagger-rust-native-plan-decoder')/name,'source/'+Path(name).name+'.gz')
(root/'revisions.json').write_text(json.dumps(dict(baseline='f73c5614a89968afa6f6000328e96ea33745fd93',candidate=subprocess.check_output(['git','-C','/tmp/dagger-rust-native-plan-decoder','rev-parse','HEAD'],text=True).strip(),engine_sha256='f61dfab5738e8f074c805da62a9e1224eebaf448f59c16399bf1953a6278eb04',selected_native_baseline='f73c5614a89968afa6f6000328e96ea33745fd93',decision='Keep decoder isolated: component gain does not establish robust complete-command benefit. No PR.',component_platform='Go1.26.6 linux/amd64 GOMAXPROCS8',actual_modules_use_same_engine_and_telemetry=True,notes='Adjust paths and receiver addresses when reproducing. Worker tool builds use CGO_ENABLED=0, -buildvcs=false, -trimpath, -ldflags=-s -w. Canonical encodings retain encoding/json.'),indent=2)+'\n')
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
