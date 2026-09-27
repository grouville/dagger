"""Local-only diagnostic: 3 primers, 7 CLI CPU/Go-trace captures, 1 separate engine wcprof capture. No ordinary latency claim."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,resource,shutil,signal,subprocess,sys,time
from urllib.error import HTTPError
HERE=Path(__file__).resolve().parent;LAB=Path('/tmp/collections-perf/engine-allocation-round2');sys.path.insert(0,str(LAB));import experiment as x
MANIFEST=Path('/tmp/collections-perf/cli-log-overlap-v3/backport-v016/builds/manifest.json')
ORIGINAL='56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12';ENGINE='9912b76324d1015e6811ea3a8ac7bdfb029ce6c079226c9a3b7aa6de8a3212a5';CLI='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
FLOWS={'core':['-m','core','api','call','version'],'module':['-m','./module','api','call','read'],'checks':['check','-l','--all']}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:print(json.dumps({'execute':False,'commands':11,'production_cloud_commands':0,'CPU_profiles':7,'wcprof_captures':1,'engine':'same owned engine/retained volume, temporary9912binary then restored','instrumented_latency_not_benchmark':True}));return
 os.umask(0o077);built=json.loads(MANIFEST.read_text());assert built['engine']['sha256']==ENGINE and x.sha(built['engine']['path'])==ENGINE
 cli=built['variants']['baseline'];assert cli['sha256']==CLI and x.sha(cli['path'])==CLI
 original=json.loads((LAB/'lazy-core-runtime-v1/engines.json').read_text())['lazy'];assert original['sha256']==ORIGINAL;x.OWNER='collections-lazy-core-runtime-v1';assert not x.owned(original)['State']['Running']
 app=LAB/'greetings';native=LAB/'native';core=Path('/tmp/collections-perf/sdk-edit-audit/core-typeref-intern-v1/first-consumer-local-v1/workspace');cwd={'core':core,'module':native,'checks':app}
 expected={'core':Path('/tmp/collections-perf/sdk-edit-audit/core-typeref-intern-v1/first-consumer-local-v1/01-first-metadata/stdout.txt').read_bytes(),'module':(native/'input.txt').read_bytes(),'checks':Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()}
 before={k:x.fixture_hashes(v)for k,v in cwd.items()};assert before['checks']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256'];assert shutil.disk_usage(HERE).free>16*1024**3
 out=HERE/'local-v1';assert not out.exists();out.mkdir();(out/'empty-config').mkdir();(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 env={k:os.environ[k]for k in ('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0',XDG_CONFIG_HOME=str(out/'empty-config'))
 backup=out/'original-engine.private';item=dict(original,sha256=ENGINE);modified=False;rows=[]
 x.write(out/'provenance.json',{'cli':cli,'engine':built['engine'],'driver_sha256':x.sha(__file__),'build_manifest_sha256':x.sha(MANIFEST),'fixtures':before,'profiling':'CPUPROFILE also enables Go execution trace; starts at PersistentPreRunE after package init/Cobra parsing, captures parent only; RUSAGE_CHILDREN covers waited tree; subtracting them does not isolate Docker; wcprof uses separate invocation; no ordinary latency claim','baseline_hypothesis':'170ms core /540ms listing CLI child CPU observed during real-local-API matrix, now isolate computation with export disabled','production_cloud_commands':0})
 def run(flow,kind):
  assert len(rows)<11 and all(x.fixture_hashes(cwd[k])==v for k,v in before.items());dest=out/f'{len(rows):02d}-{flow}-{kind}';dest.mkdir();command=[cli['path'],'--engine','container://'+item['name']]+(['--profile']if kind=='wcprof'else[])+FLOWS[flow];childenv=dict(env)
  if kind=='cpu':childenv['CPUPROFILE']=str(dest/'cli.pprof')
  if kind=='wcprof':
   try:(dest/'prior.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
   except HTTPError as e:
    if e.code!=503:raise
  with(dest/'stdout.private').open('wb')as stdout,(dest/'stderr.private').open('wb')as stderr:
   usage_before=resource.getrusage(resource.RUSAGE_CHILDREN);begin=time.monotonic();proc=subprocess.Popen(command,cwd=cwd[flow],env=childenv,stdout=stdout,stderr=stderr,start_new_session=True)
   try:code=proc.wait(timeout=120)
   finally:
    if proc.poll()is None:
     proc.send_signal(signal.SIGINT)
     try:proc.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
  elapsed=time.monotonic()-begin;usage_after=resource.getrusage(resource.RUSAGE_CHILDREN);correct=code==0 and(dest/'stdout.private').read_bytes()==expected[flow]
  if kind=='wcprof':(dest/'run.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
  row={'flow':flow,'kind':kind,'seconds_instrumented':elapsed,'process_tree_user_seconds':usage_after.ru_utime-usage_before.ru_utime,'process_tree_system_seconds':usage_after.ru_stime-usage_before.ru_stime,'correct':correct,'exit_code':code,'stdout_sha256':x.sha(dest/'stdout.private')};rows.append(row);x.write(out/'results.json',rows);print(json.dumps(row),flush=True);assert correct
  if kind=='cpu':assert(dest/'cli.pprof').stat().st_size>0 and(dest/'cli.pprof.trace').stat().st_size>0
 try:
  x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(backup)]);assert x.sha(backup)==ORIGINAL;modified=True;x.capture(['docker','cp',built['engine']['path'],item['name']+':/usr/local/bin/dagger-engine']);x.start(item)
  for flow,n in [('core',3),('module',2),('checks',2)]:
   run(flow,'primer')
   for _ in range(n):run(flow,'cpu')
  run('checks','wcprof')
 finally:
  if modified:
   if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
   x.capture(['docker','cp',str(backup),item['name']+':/usr/local/bin/dagger-engine']);verify=out/'restored-engine.private';x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(verify)]);assert x.sha(verify)==ORIGINAL
  unchanged=all(x.fixture_hashes(cwd[k])==v for k,v in before.items());x.write(out/'restoration.json',{'fixtures_unchanged':unchanged,'original_engine_restored':modified,'engine_stopped':not x.owned(item)['State']['Running'],'validated_commands':sum(r['correct']for r in rows),'production_cloud_commands':0,'resources_deleted':0});assert unchanged
 assert len(rows)==11
if __name__=='__main__':main()
