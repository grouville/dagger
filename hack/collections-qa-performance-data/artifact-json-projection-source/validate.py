#!/usr/bin/env python3
"""Prepared bounded offline gates; execute only after parent grants the slot."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
P=Path(__file__).resolve().parent;ROOT=Path('/home/dagger/dag')
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
PATTERN='^(TestArtifactJSONProjection.*|TestArtifactListReusesWorkspaceWithGlobalAliases|TestListedArtifactKeysPreservesDimensionAndOrder)$'
a=argparse.ArgumentParser(description=__doc__);a.add_argument('--run',action='store_true');args=a.parse_args()
if not args.run:
 print(json.dumps({'execute':False,'scope':'one focused baseline-negative plus candidate normal/race CLI tests, including real SDK helper','engine_calls':0,'cloud_calls':0}));raise SystemExit(0)
manifest=json.loads((P/'manifest.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for section in ('production','tests'):
 for name,facts in manifest[section].items():
  source=ROOT/name
  assert(sha(source)if source.exists()else None)==facts['baseline_sha256']
  overlay=json.loads((P/'test-overlay.json').read_text())['Replace'];assert sha(overlay[str(source)])==facts['candidate_sha256']
out=P/'validation-v1';assert not out.exists();out.mkdir();rows=[]
for label,overlay,pattern,flags in [
 ('baseline-negative','negative-overlay.json','^TestArtifactJSONProjectionSingleRequestAndOrder/check$',[]),
 ('candidate-normal','test-overlay.json',PATTERN,[]),
 ('candidate-race','test-overlay.json',PATTERN,['-race']),
]:
 command=[GO,'test',*flags,'-json','-mod=readonly','-modfile='+MOD,'-overlay='+str(P/overlay),'-count=1','-timeout=90s','-run='+pattern,'./internal/cmd/dagger']
 begin=time.monotonic()
 with(out/(label+'.private.log')).open('wb')as log:
  proc=subprocess.run(command,cwd=ROOT,env={**os.environ,'GOTOOLCHAIN':'local','GOPROXY':'off','GOSUMDB':'off'},stdout=log,stderr=subprocess.STDOUT,timeout=240)
 events=[]
 for line in(out/(label+'.private.log')).read_text().splitlines():
  try:events.append(json.loads(line))
  except json.JSONDecodeError:pass
 passed=[e['Test']for e in events if e.get('Action')=='pass'and'Test'in e]
 failed=[e['Test']for e in events if e.get('Action')=='fail'and'Test'in e]
 witness=label=='baseline-negative'
 valid=(proc.returncode!=0 and failed==['TestArtifactJSONProjectionSingleRequestAndOrder/check','TestArtifactJSONProjectionSingleRequestAndOrder']and'an intermediate artifact ID request is unnecessary'in(out/(label+'.private.log')).read_text())if witness else(proc.returncode==0 and bool(passed)and not failed)
 row={'step':label,'command':command,'exit_code':proc.returncode,'wall_seconds':time.monotonic()-begin,'pass':passed,'fail':failed,'expected_outcome':valid,'log_sha256':sha(out/(label+'.private.log'))}
 rows.append(row);(out/'results.json').write_text(json.dumps({'steps':rows,'engine_calls':0,'cloud_calls':0},indent=2)+'\n');print(json.dumps(row),flush=True)
 assert valid,'unexpected gate result; preserve this attempt before correcting anything'
