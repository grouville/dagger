"""Prepare-only unless --run: four LOCAL commands on two newly owned volumes.

One baseline/candidate fresh-volume pair, each followed by its own warm repeat.
Image, SDK blobs and host page cache are available. No Cloud, build or image pull.
"""
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
import argparse,hashlib,json,os,re,resource,shutil,signal,subprocess,threading,time,uuid
P=Path(__file__).resolve().parent;REPO=Path('/home/dagger/dag');LAB=Path('/tmp/collections-perf')
APP=LAB/'engine-allocation-round2/greetings';BUILDS=LAB/'ancestor-request-v1/builds/runtime-builds.json';RECIPE=LAB/'ancestor-request-v1/builds/build-recipe.json'
IMAGE='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
SDK='sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef'
OWNER='collections-ancestor-request-cold-v1';MIN_FREE=16*1024**3;MAX_WRITE=8*1024**3;CAP=4
HTTP=build_opener(ProxyHandler({}));LABEL='dagger.perf.owner'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def capture(a):return subprocess.check_output(a,text=True).strip()
def inspect(kind,name):return json.loads(capture(['docker',kind,'inspect',name]))[0]
def exists(kind,name):return subprocess.run(['docker',kind,'inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def fixtures():
 d={}
 for directory,names,files in os.walk(APP):
  names[:]=[x for x in names if x not in ('.git','node_modules')]
  for n in files:
   p=Path(directory)/n
   if p.is_file():d[str(p.relative_to(APP))]=sha(p)
 return d
def pressure():return {k:{l.split()[0]:int(l.rsplit('=',1)[1])for l in Path('/proc/pressure',k).read_text().splitlines()}for k in ('cpu','io','memory')}
def owned(item):
 i=inspect('container',item['id']);assert i['Id']==item['id']and i['Config']['Labels'].get(LABEL)==OWNER
 m=[m for m in i['Mounts']if m['Destination']=='/var/lib/dagger'];assert len(m)==1 and m[0]['Type']=='volume'and m[0]['Name']==item['name']
 return i
def volume_owned(item):
 v=inspect('volume',item['name']);assert v['Labels'].get(LABEL)==OWNER and v['CreatedAt']==item['volume_created_at'];return v
def group_for(item):
 pid=owned(item)['State']['Pid'];assert pid>0
 group=Path('/sys/fs/cgroup')/Path('/proc',str(pid),'cgroup').read_text().split('::')[1].strip().lstrip('/')
 return group.parent if group.name=='init'else group
def io_totals(group):
 result={}
 for l in (group/'io.stat').read_text().splitlines():
  for k,v in (x.split('=')for x in l.split()[1:]):result[k]=result.get(k,0)+int(v)
 return result
def diskstats():
 return {v[2]:[int(x)for x in v[3:]]for l in Path('/proc/diskstats').read_text().splitlines()for v in [l.split()]if re.fullmatch(r'(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+)',v[2])}
def snapshot(group):
 return {'host_diskstats':diskstats(),'engine_io':io_totals(group),'engine_cpu':{l.split()[0]:int(l.split()[1])for l in(group/'cpu.stat').read_text().splitlines()},'host_psi_us':pressure(),'free_disk_bytes':shutil.disk_usage(P).free,'host_dirty_writeback_kib':{s.split()[0].rstrip(':'):int(s.split()[1])for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith(('Dirty:','Writeback:'))}}
def delta(a,b):
 return {'host_diskstats_delta':{d:[y-x for x,y in zip(a['host_diskstats'][d],b['host_diskstats'][d])]for d in a['host_diskstats']if d in b['host_diskstats']},'engine_io':{k:b['engine_io'].get(k,0)-a['engine_io'].get(k,0)for k in set(a['engine_io'])|set(b['engine_io'])},'engine_cpu':{k:b['engine_cpu'][k]-a['engine_cpu'][k]for k in a['engine_cpu']},'host_psi_us':{k:{q:b['host_psi_us'][k][q]-a['host_psi_us'][k][q]for q in a['host_psi_us'][k]}for k in a['host_psi_us']},'free_disk_start':a['free_disk_bytes'],'free_disk_end':b['free_disk_bytes'],'host_dirty_writeback_start_kib':a['host_dirty_writeback_kib'],'host_dirty_writeback_end_kib':b['host_dirty_writeback_kib']}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
 if not args.run:
  print(json.dumps({'run':False,'commands':4,'cloud_commands':0,'order':['baseline-cold','baseline-warm','candidate-cold','candidate-warm'],'new_volumes':2,'image':IMAGE,'minimum_free_bytes':MIN_FREE,'engine_write_guard_bytes':MAX_WRITE,'scope':'single fresh Dagger-volume pair; host/image/blob caches retained; startup separate; no uniform cold-performance claim'}));return
 os.umask(0o077);out=P/'results-v1';assert not out.exists();out.mkdir();(out/'empty-config').mkdir(mode=0o700)
 assert sha(BUILDS)=='c10bb9d81a1146bb4d885820108b2e7969278be38e37d33663a23ba5fd1bf6e7'
 build=json.loads(BUILDS.read_text());assert sha(RECIPE)==build['recipe_sha256']
 assert build['source_head']=='85b60f7a0a16a27459ef571bc94bcf870c876dcc'and build['wcprof_marker']=='filesync.syncParentDirs'
 assert build['variants']['baseline']['cli']['sha256']=='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
 for variant in ('baseline','candidate'):
  for role in ('cli','engine'):
   b=build['variants'][variant][role];assert sha(b['path'])==b['sha256']
 image=inspect('image',IMAGE);assert image['Id']==IMAGE
 forbidden=('DAGGER_CLOUD','OTEL_','_EXPERIMENTAL_DAGGER_CACHE','AWS_','GOOGLE_APPLICATION_CREDENTIALS')
 assert not any(e.partition('=')[0].startswith(forbidden)for e in image['Config'].get('Env',[])),'unexpected ambient image export/cache credentials; no values recorded'
 wanted=(REPO/'hack/collections-qa-performance-data/expected-checks.txt').read_bytes();assert len(wanted.splitlines())==14
 original=fixtures();assert original==json.loads((LAB/'engine-allocation-round2/withfile-v1/prepared.json').read_text())['input_sha256']
 blobdirs=[LAB/'prebuilt-ts-sdk/blobs',LAB/'half-second/node-compile/blobs'];blobs={}
 for d in blobdirs:
  for p in d.iterdir():
   if not p.is_file():continue
   if p.name in blobs:assert sha(p)==sha(blobs[p.name])
   blobs[p.name]=p
 env={k:os.environ[k]for k in ('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(XDG_CONFIG_HOME=str(out/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
 assert not any(k.startswith(('DAGGER_CLOUD','OTEL_'))for k in env)
 nonce=uuid.uuid4().hex[:10];items=[];rows=[];attempts=[];stops=[];write_total=0
 provenance={'image':IMAGE,'sdk_manifest':SDK,'build_manifest':build,'build_manifest_sha256':sha(BUILDS),'build_recipe_sha256':sha(RECIPE),'source_sha256':sha(__file__),'fixture_hashes_before':original,'sdk_blob_hashes':{p.name:sha(p)for p in blobs.values()},'expected_stdout_sha256':hashlib.sha256(wanted).hexdigest(),'cloud_commands':0,'command_cap':CAP,'cache_boundary':'Each first CLI starts on a newly created empty named Dagger volume; SDK image/blobs and host pages are retained, image pulls/builds are not part of setup. Engine start through debug readiness is separately recorded. First CLI is check -l --all, not preceded by a Dagger request.','order':'Baseline then candidate; one pair, order-confounded diagnostic, not a variability estimate. Each has one identical warm repeat.','timing':'Popen through blocking waitpid. Setup, binary/blob copies, engine readiness, source guards and host/cgroup snapshots excluded. Counters sampled around CLI and write guard every500ms.','bounds':{'free_disk_bytes':MIN_FREE,'engine_written_bytes':MAX_WRITE,'command_timeout_seconds':300,'write_guard_scope':'Cumulative engine cgroup writes from process creation, plus prior stopped engine final sample; sampled guard is not a hard I/O quota. Final stop writeback may follow last sample.'},'cleanup':'Only exact newly created IDs/names with owner labels and volume creation timestamps; remove these two containers/volumes after evidence capture. Never modify existing engines.'}
 write(out/'provenance.json',provenance);(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 def guard():assert shutil.disk_usage(P).free>MIN_FREE and write_total<MAX_WRITE and fixtures()==original
 try:
  # Prepare both owned containers before either cold CLI, outside all CLI timers.
  for variant in ('baseline','candidate'):
   guard();name=f'dagger-engine.collections-parent-cold-{nonce}-{variant}';assert not exists('container',name)and not exists('volume',name)
   capture(['docker','volume','create','--label',LABEL+'='+OWNER,name]);v=inspect('volume',name)
   item={'name':name,'variant':variant,'volume_created_at':v['CreatedAt'],'id':None};items.append(item);write(out/'resources.json',items)
   cid=capture(['docker','create','--name',name,'--label',LABEL+'='+OWNER,'--privileged','-p','127.0.0.1::6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+SDK,'-e','_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=',IMAGE,'--debugaddr=0.0.0.0:6060'])
   item['id']=cid;write(out/'resources.json',items);owned(item);volume_owned(item)
   capture(['docker','cp',build['variants'][variant]['engine']['path'],cid+':/usr/local/bin/dagger-engine'])
   for filename,path in blobs.items():capture(['docker','cp',str(path),cid+':/usr/local/share/dagger/content/blobs/sha256/'+filename])
  for item in items:
   guard();info=owned(item);assert info['State']['Status']=='created','cold resource previously started';variant=item['variant']
   begin=time.monotonic();capture(['docker','start',item['id']]);info=owned(item);port=int(info['NetworkSettings']['Ports']['6060/tcp'][0]['HostPort']);item['port']=port
   for _ in range(300):
    try:
     with HTTP.open(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
    except OSError:time.sleep(.1)
   else:raise TimeoutError('engine readiness')
   ready=time.monotonic()-begin
   assert capture(['docker','exec',item['id'],'sha256sum','/usr/local/bin/dagger-engine']).split()[0]==build['variants'][variant]['engine']['sha256']
   group=group_for(item)
   for phase in ('cold','warm'):
    guard();assert len(attempts)<CAP;dest=out/f'{variant}-{phase}';dest.mkdir();attempts.append({'variant':variant,'phase':phase});write(out/'attempts.json',attempts)
    before=snapshot(group);assert write_total+before['engine_io'].get('wbytes',0)<MAX_WRITE
    command=[build['variants'][variant]['cli']['path'],'--engine','container://'+item['name'],'check','-l','--all'];done=threading.Event();obs={};reason=None;usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    with(dest/'stdout.private').open('wb')as stdout,(dest/'stderr.private').open('wb')as stderr:
     begin=time.monotonic();wall=time.time_ns();proc=subprocess.Popen(command,cwd=APP,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
     def waiter():obs.update(code=proc.wait(),end=time.monotonic(),wall=time.time_ns());done.set()
     thread=threading.Thread(target=waiter,daemon=True);thread.start()
     try:
      while not done.wait(.5):
       if time.monotonic()-begin>300:reason='command timeout';break
       if shutil.disk_usage(P).free<=MIN_FREE:reason='free disk floor';break
       if write_total+io_totals(group).get('wbytes',0)>=MAX_WRITE:reason='engine write guard';break
     finally:
      if not done.is_set():
       try:proc.send_signal(signal.SIGINT)
       except ProcessLookupError:pass
       if not done.wait(10):
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
      thread.join(15);assert not thread.is_alive()
    after=snapshot(group);cpu=resource.getrusage(resource.RUSAGE_CHILDREN);stdout=(dest/'stdout.private').read_bytes();text=(dest/'stderr.private').read_bytes()
    cloud_urls=re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*',stdout+b'\n'+text);unexpected=any(u.rstrip(b'.')!=b'https://dagger.cloud/traces/setup'for u in cloud_urls)
    correct=reason is None and obs['code']==0 and stdout==wanted and not unexpected
    row={'variant':variant,'phase':phase,'seconds':obs['end']-begin,'started_unix_ns':wall,'exited_unix_ns':obs['wall'],'engine_start_to_ready_seconds_excluded':ready,'exit_code':obs['code'],'guard_abort':reason,'correct':correct,'stdout_sha256':sha(dest/'stdout.private'),'stdout_rows':len(stdout.splitlines()),'unexpected_cloud_link':unexpected,'process_tree_user_seconds':cpu.ru_utime-usage.ru_utime,'process_tree_system_seconds':cpu.ru_stime-usage.ru_stime,**delta(before,after)}
    rows.append(row);write(out/'results.json',rows);print(json.dumps({k:row[k]for k in ('variant','phase','seconds','correct','engine_io')}),flush=True);assert correct,'cold command validation failed; retained private output'
    assert write_total+after['engine_io'].get('wbytes',0)<MAX_WRITE;guard()
   final=snapshot(group);write_total+=final['engine_io'].get('wbytes',0);write(out/f'{variant}-final-counters.json',final)
   capture(['docker','stop','--timeout','30',item['id']]);assert not owned(item)['State']['Running'];stops.append(variant)
 finally:
  cleanup=[]
  for item in items:
   record={'variant':item['variant'],'container_removed':not exists('container',item['name'])if item['id']is None else False,'volume_removed':False}
   try:
    if item['id']:
     i=owned(item)
     if i['State']['Running']:capture(['docker','stop','--timeout','30',item['id']])
     capture(['docker','rm',item['id']]);record['container_removed']=not exists('container',item['id'])
    volume_owned(item);capture(['docker','volume','rm',item['name']]);record['volume_removed']=not exists('volume',item['name'])
   except Exception as e:record['cleanup_error_type']=type(e).__name__
   cleanup.append(record)
  restored=fixtures()==original;write(out/'cleanup.json',{'created_resources':cleanup,'fixture_unchanged':restored,'attempts':len(attempts),'valid_commands':sum(r['correct']for r in rows),'cloud_commands':0,'engine_written_bytes_before_final_stops':write_total})
  assert restored and all(r['container_removed']and r['volume_removed']for r in cleanup),'cleanup incomplete; inspect exact owned resources only'
 assert len(rows)==CAP and all(r['correct']for r in rows)
if __name__=='__main__':main()
