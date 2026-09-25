from pathlib import Path
import hashlib,json,shutil,subprocess
b=Path('/tmp/collections-perf/discovery-next');dest=Path('/home/dagger/dag/hack/collections-qa-performance-data/artifact-schema-fork');dest.mkdir(exist_ok=True)
files=set()
for folder in ['warm','cold','invalidation','control-wcprof','candidate-wcprof','candidate-cpu','cli-floor']:
 for p in (b/folder).rglob('*'):
  if p.is_file() and (p.suffix in ['.py','.json','.jsonl','.out','.err'] or p.suffix=='.txt'):files.add(p)
for p in b.iterdir():
 if p.is_file() and (p.suffix in ['.py','.sh','.json','.jsonl','.txt'] or p.name in ['unit.log','benchmark.log','invalidate.log','compare-profiles.log','cold.log','candidate-profile.log']):files.add(p)
for p in files:
 out=dest/p.relative_to(b);out.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix in ['.txt','.log']:out.write_text(p.read_text().rstrip()+'\n')
 else:shutil.copyfile(p,out)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()
external=[b/'engine',b/'engine.cpu',b/'candidate-cpu/engine.cpu',b/'integration.log',b/'cli-floor/profile.cpu',b/'cli-floor/profile.cpu.trace',b/'cli-floor/profile-sync.pprof',Path('/tmp/collections-perf/schema-decode/engine'),Path('/tmp/collections-perf/committed/dagger'),Path('/tmp/collections-perf/half-second/integration.test')]+list(b.rglob('runs.wcprof'))
source=Path('/home/dagger/dag');patch=subprocess.check_output(['git','diff','--','core/modtree.go','core/schema_build.go'],cwd=source)
provenance={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),'source_diff_sha256':hashlib.sha256(patch).hexdigest(),'application_commit':'14d684fccf75a137de96f3f0c7eb8c6dafef2d3e','go_module_commit':'1784ff37eb3dd1aacab7aaff91b1d86e311cc8de','workspace':'/tmp/collections-perf/normal-baseline/greetings-split','candidate_build_command':'CGO_ENABLED=0 go build -buildvcs=false -modfile=/tmp/collections-perf/rebuilt-prototypes/engine.mod -overlay=/tmp/collections-perf/schema-decode/overlay.json -o /tmp/collections-perf/discovery-next/engine ./cmd/engine','source_files':{str(p.relative_to(source)):sha(p) for p in [source/'core/modtree.go',source/'core/schema_build.go']},'external_files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in external if p.exists()]}
(dest/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('archived',len(files),'files plus provenance')
