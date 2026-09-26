#!/usr/bin/env python3
"""Matched5/100ms Cloud coalescing, unchanged instrumented v2 relay."""
import argparse,hashlib,json,os,statistics,subprocess,time,urllib.request
from pathlib import Path
BASE=Path('/tmp/collections-perf/telemetry-relay'); HERE=Path(__file__).resolve().parent
GAUGES={'Pending','Bytes','CleanupPending','Tombstones','LastStatus','OldestPendingNS','ExportActive','ExportPeak'}
ENGINES={5:('dagger-engine.collections-disk-abba-2',6172,'a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5'),100:('dagger-engine.collections-disk-abba-1',6171,None)}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
 return h.hexdigest()
def run(cmd):return subprocess.check_output(cmd,text=True).strip()
def delta(a,b):return {k:b[k]-a[k] for k in b if isinstance(b[k],int) and k not in GAUGES}
def psi(p):return int(Path(p).read_text().splitlines()[1].rsplit('=',1)[1])
def snapshot(cg):
 mem={a.rstrip(':'):int(v) for a,v,*_ in map(str.split,Path('/proc/meminfo').read_text().splitlines())}
 io={s[0]:{k:int(v) for k,v in (p.split('=') for p in s[1:])} for s in map(str.split,(cg/'io.stat').read_text().splitlines())}
 return {'host_io_full_us':psi('/proc/pressure/io'),'engine_io_full_us':psi(cg/'io.pressure'),'engine_io':io,'dirty_kib':mem['Dirty'],'writeback_kib':mem['Writeback']}
def main():
 p=argparse.ArgumentParser();p.add_argument('--trial',required=True);p.add_argument('--pairs',type=int,default=4);p.add_argument('--burst',type=int,default=10);p.add_argument('--warmups',type=int,default=2);p.add_argument('--profiles',action='store_true');a=p.parse_args()
 assert '/' not in a.trial and a.trial not in ['', '.', '..']
 dest=HERE/a.trial;dest.mkdir(mode=0o700,exist_ok=False)
 spool=BASE/('private-spool-'+a.trial);assert not spool.exists()
 config=json.loads((BASE/'config.json').read_text());assert config['target']=='https://api.dagger.cloud'
 admin=(BASE/'admin-token').read_text().strip()
 for name,want in json.loads((BASE/'relay-v2-validation.json').read_text())['sha256'].items():assert sha(BASE/name)==want,'tested relay changed'
 cli=Path('/tmp/collections-perf/rebase-main/dagger');ws=Path('/tmp/collections-perf/sdk-edit-audit/ts-static/greetings')
 want=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
 cgroups={};engmeta={}
 for delay,(name,port,expected) in ENGINES.items():
  expected=expected or sha(HERE/'engine-100ms')
  actual=run(['docker','exec',name,'sha256sum','/usr/local/bin/dagger-engine']).split()[0];assert actual==expected
  pid=run(['docker','inspect','--format','{{.State.Pid}}',name]);cg=Path('/sys/fs/cgroup')/Path('/proc',pid,'cgroup').read_text().split('::')[1].strip().lstrip('/')
  cgroups[delay]=cg.parent if cg.name=='init' else cg;engmeta[delay]={'name':name,'sha256':actual,'port':port}
 fixture={name:sha(ws/name) for name in ['dagger.toml','dagger.lock','main_test.go','main.go','.dagger/modules/backend/main.go','.dagger/modules/frontend/.dagger-static-types/main.dang','.dagger/modules/frontend/.dagger-static-types/manifest.json'] if (ws/name).is_file()}
 env=dict(os.environ)
 for key in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN']:env.pop(key,None)
 env['DAGGER_CLOUD_URL']=config['endpoint']
 (dest/'provenance.json').write_text(json.dumps({'engines':engmeta,'cli':str(cli),'cli_sha256':sha(cli),'workspace':str(ws),'fixture_sha256':fixture,'relay_sha256':sha(BASE/'relay'),'relay_source_sha256':sha(BASE/'main.go'),'driver_sha256':sha(__file__),'argv':['check','-l','--all'],'modes':['sync-relay','async-relay'],'warmups_per_configuration':a.warmups,'pairs_per_mode':a.pairs,'burst_commands_per_configuration':a.burst,'profiles':a.profiles,'timing':'CLI through exit; full observed drain includes200msstablezero; postexitstats are sampled'},indent=2)+'\n')
 def request(path,method='GET'):
  req=urllib.request.Request(config['endpoint']+path,method=method,headers={'X-Relay-Admin':admin})
  with urllib.request.urlopen(req,timeout=5) as r:data=r.read()
  return json.loads(data) if data else None
 def healthy(s):
  assert all(s[k]==0 for k in ['Failed','StorageErrors','ExportErrors','Export4xx','Export5xx','ExportOther']),s
 def drained():
  empty=None;previous=None;started=time.monotonic()
  while True:
   s=request('/relay/stats');healthy(s)
   key=tuple(s[k] for k in ['Accepted','Delivered','ExportRequests','Export2xx'])
   if all(s[k]==0 for k in ['Pending','Bytes','CleanupPending','ExportActive']):
    if empty is None or key!=previous:empty=time.monotonic()
    elif time.monotonic()-empty>=.2:return s
    previous=key
   else:empty=None
   assert time.monotonic()-started<120, 'delivery timeout'
   time.sleep(.05)
 rows=[];blocks=[];relay=None;log=(dest/'relay.log').open('ab')
 def execute(delay,mode,phase,i,before,origin,profile=False):
  name,port,_=ENGINES[delay];tag=f'{phase}-{mode}-{delay}ms-{i}';renv=dict(env)
  cmd=[str(cli),'--engine','container://'+name]
  if profile:cmd+=['--profile'];renv['CPUPROFILE']=str(dest/(tag+'.cpu'))
  cmd+=['check','-l','--all'];io_before=snapshot(cgroups[delay]);started=time.monotonic()
  r=subprocess.run(cmd,cwd=ws,env=renv,capture_output=True,timeout=180);exited=time.monotonic();io_after=snapshot(cgroups[delay])
  s=request('/relay/stats');sampled=time.monotonic();healthy(s)
  (dest/(tag+'.out')).write_bytes(r.stdout);(dest/(tag+'.err')).write_bytes(r.stderr)
  assert r.returncode==0 and r.stdout==want, 'incorrect listing'
  row={'delay_ms':delay,'mode':mode,'phase':phase,'iteration':i,'seconds':exited-started,'start_from_phase_seconds':started-origin,'exit_from_phase_seconds':exited-origin,'postexit_sample_delay_seconds':sampled-exited,'correct':True,'status':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'relay_before':before,'relay_postexit':s,'interval_delta':delta(before,s),'host_io_full_seconds':(io_after['host_io_full_us']-io_before['host_io_full_us'])/1e6,'engine_io_full_seconds':(io_after['engine_io_full_us']-io_before['engine_io_full_us'])/1e6,'io_before':io_before,'io_after':io_after}
  return row
 def finish(row,before,mode,origin):
  after=drained();end=time.monotonic();d=delta(before,after)
  assert d['ExportRequests']==d['Export2xx']>0
  if mode=='async':assert d['Accepted']==d['Delivered']>0
  row.update(relay_after_drain=after,relay_delta=d,observed_full_seconds=end-origin,postexit_to_observed_stablezero_seconds=end-origin-row['exit_from_phase_seconds'])
 def save(row):
  rows.append(row);(dest/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
  print(json.dumps({k:row[k] for k in ['phase','mode','delay_ms','iteration','seconds']}|{'pending':row['relay_postexit']['Pending'],'requests':row.get('relay_delta',{}).get('ExportRequests')}),flush=True)
 try:
  relay=subprocess.Popen([str(BASE/'relay'),'--listen',config['listen'],'--target',config['target'],'--spool',str(spool),'--admin-file',str(BASE/'admin-token')],stdout=log,stderr=log)
  for _ in range(100):
   assert relay.poll() is None
   try:
    s=request('/relay/stats');assert s['Accepted']==s['ExportRequests']==0;time.sleep(.1);assert relay.poll() is None;break
   except OSError:time.sleep(.05)
  else:raise RuntimeError('relay startup failed')
  for i in range(-a.warmups,a.pairs):
   modes=['sync','async'] if i%2==0 else ['async','sync']
   for mode in modes:
    for delay in ([5,100] if i%2==0 else [100,5]):
     before=drained();request('/relay/mode?value='+mode,'POST');origin=time.monotonic()
     row=execute(delay,mode,'pair',i,before,origin);finish(row,before,mode,origin);save(row)
  # Reverse variant order between modes; only one block/configuration.
  for mode,delay in [('async',5),('async',100),('sync',100),('sync',5)]:
   before=drained();request('/relay/mode?value='+mode,'POST');previous=before;origin=time.monotonic();group=[]
   for i in range(a.burst):
    row=execute(delay,mode,'burst',i,previous,origin);save(row);group.append(row);previous=row['relay_postexit']
   block={'mode':mode,'delay_ms':delay,'commands':a.burst,'exit_from_phase_seconds':group[-1]['exit_from_phase_seconds'],'pending_postexit':[r['relay_postexit']['Pending'] for r in group],'bytes_postexit':[r['relay_postexit']['Bytes'] for r in group],'oldest_pending_seconds_postexit':[r['relay_postexit']['OldestPendingNS']/1e9 for r in group]}
   finish(block,before,mode,origin);blocks.append(block);(dest/'burst-summary.json').write_text(json.dumps(blocks,indent=2)+'\n');print(json.dumps({'block':block}),flush=True)
  if a.profiles:
   for mode,delay in [('sync',5),('sync',100),('async',100),('async',5)]:
    before=drained();request('/relay/mode?value='+mode,'POST');origin=time.monotonic();row=execute(delay,mode,'profile',0,before,origin,profile=True);finish(row,before,mode,origin);save(row)
    with urllib.request.urlopen(f'http://127.0.0.1:{ENGINES[delay][1]}/debug/wcprof/dump',timeout=60) as response:(dest/f'profile-{mode}-{delay}ms.wcprof').write_bytes(response.read())
  summary={}
  for mode in ['sync','async']:
   for delay in [5,100]:
    selected=[r for r in rows if r['phase']=='pair' and r['iteration']>=0 and r['mode']==mode and r['delay_ms']==delay]
    summary[f'{mode}-{delay}ms']={'n':len(selected),'median_cli_seconds':statistics.median(r['seconds'] for r in selected),'median_observed_full_seconds':statistics.median(r['observed_full_seconds'] for r in selected),'median_requests':statistics.median(r['relay_delta']['ExportRequests'] for r in selected),'total_requests':sum(r['relay_delta']['ExportRequests'] for r in selected),'total_bytes':sum(r['relay_delta']['ExportRequestBytes'] for r in selected)}
  (dest/'paired-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'summary':summary}),flush=True)
  assert all(sha(ws/name)==value for name,value in fixture.items()),'fixture changed'
 finally:
  if relay is not None and relay.poll() is None:
   try:
    s=request('/relay/stats');(dest/'final-stats.json').write_text(json.dumps(s,indent=2)+'\n')
    if all(s[k]==0 for k in ['Pending','Bytes','CleanupPending','ExportActive']):relay.terminate();relay.wait(timeout=5);(dest/'relay-stopped.json').write_text(json.dumps({'stopped':True,'exit_status':relay.returncode})+'\n')
    else:print(json.dumps({'relay_retained_for_delivery':relay.pid,'stats':s}),flush=True)
   except Exception:print(json.dumps({'relay_retained_unknown_state':relay.pid}),flush=True)
  log.close()
if __name__=='__main__':main()
