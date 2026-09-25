from pathlib import Path
import json,hashlib,shutil,subprocess
b=Path('/tmp/collections-perf/cli-boundaries');repo=Path('/home/dagger/dag');d=repo/'hack/collections-qa-performance-data/cli-boundaries';d.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
files=[]
for folder in ['warm','warm-http1','control-wcprof','early-analytics-wcprof']:
 for p in (b/folder).rglob('*'):
  if p.is_file() and p.suffix in ['.json','.out','.txt']:files.append(p)
for pattern in ['run-*.json','run-*.jsonl','diag-*.json','diag-*.jsonl']:
 files+=list(b.glob(pattern))
for name in ['prepare.py','prepare-batch.py','bench.py','diagnose.py','summarize-timelines.py','archive.py','otel-batch-prototype.patch','timelines-summary.json','analytics-test.log','analytics-race-final.log','batch-sdk-test.log']:
 files.append(b/name)
for p in files:
 q=d/p.relative_to(b);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
external=[p for p in b.glob('dagger-*') if p.is_file()]+list(b.glob('*-wcprof/runs.wcprof'))
prov={'base_commit':'f868ee9732f2d80296067314b4930bf52651ee17','candidate_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'cloud_checkout_commit':subprocess.check_output(['git','-C','/home/dagger/dagger.io','rev-parse','HEAD'],text=True).strip(),'engine':'container://dagger-engine.collections-artifact-schema-fork','workspace':'/tmp/collections-perf/normal-baseline/greetings-split','application_commit':'14d684fccf75a137de96f3f0c7eb8c6dafef2d3e','go_module_commit':'1784ff37eb3dd1aacab7aaff91b1d86e311cc8de','build_command':'CGO_ENABLED=0 go build -buildvcs=false -o CLI ./cmd/dagger','control_overlay':'HEAD before candidate:analytics/analytics.go','prototype_sdk_version':'go.opentelemetry.io/otel/sdk@v1.43.0','prototype_http1':'ForceAttemptHTTP2: false in private cloudExportTransport, otherwise early-analytics candidate','cloud_server_deployed_or_profiled':False,'external_files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in external],'raw_stderr_sha256':{str(p.relative_to(b)):sha(p) for p in b.rglob('*.err')}}
(d/'provenance.json').write_text(json.dumps(prov,indent=2)+'\n');print(len(files),'files archived')
