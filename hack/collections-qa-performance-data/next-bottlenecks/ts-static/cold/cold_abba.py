#!/usr/bin/env python3
"""Separate container preparation from an exclusive fresh-volume ABBA window."""
import argparse, hashlib, json, subprocess, sys, time, urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=Path('/home/dagger/dag')
LAB=Path('/tmp/collections-perf/post-rebase-io')
sys.path.insert(0,str(LAB))
import run as lab
WORKSPACE=Path('/tmp/collections-perf/sdk-edit-audit/ts-static/greetings')
BASE_IMAGE='localhost/dagger-engine.collections-perf:latest'
MANIFEST='sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef'
BINARIES={
 'control':('/tmp/collections-perf/sdk-edit-audit/engine-combined','b4955e7056c1e646077a2e6a8a74d77e8a6763a31e921feeb792ce5d8274dcac'),
 'static':('/tmp/collections-perf/sdk-edit-audit/ts-static/engine','a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5')}
BLOB_DIRS=[Path('/tmp/collections-perf/prebuilt-ts-sdk/blobs'),Path('/tmp/collections-perf/half-second/node-compile/blobs')]
ORDER=['control','static','static','control']

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def capture(args):return subprocess.check_output(args,text=True).strip()
def existing(kind,name):return subprocess.run(['docker',kind,'inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0

def prepare(dest,first_port,order):
 dest.mkdir(exist_ok=False)
 base_id=capture(['docker','image','inspect','--format','{{.Id}}',BASE_IMAGE])
 for path,want in BINARIES.values():assert digest(path)==want,path+' binary changed'
 blobs={str(p):digest(p) for folder in BLOB_DIRS for p in folder.iterdir() if p.is_file()}
 inputs={str(p):digest(p) for p in [lab.CLI,WORKSPACE/'main_test.go',WORKSPACE/'.dagger/modules/frontend/.dagger-static-types/main.dang',WORKSPACE/'.dagger/modules/frontend/.dagger-static-types/manifest.json']}
 prepared={'base_image':base_id,'sdk_manifest':MANIFEST,'binaries':BINARIES,'blobs_sha256':blobs,'input_sha256':inputs,'order':order,'workspace':str(WORKSPACE),'containers':[],
  'cache':'ordinary engine has no injected remote-cache integration; fixture root forced empty; CLI upstream cache import/export env unset',
  'timing':'ready task-owned engine, fresh Dagger volume; full new CLI process through exit; host page cache preserved; all container creation/binary/blob copies precede measured ABBA'}
 for i,variant in enumerate(order):
  name=f'dagger-engine.collections-{dest.name}-{i}';port=first_port+i
  assert not existing('container',name) and not existing('volume',name),'task resource already exists'
  command=['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger',
   '-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+MANIFEST,'-e','_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=',base_id,'--debugaddr=0.0.0.0:6060']
  capture(command)
  capture(['docker','cp',BINARIES[variant][0],name+':/usr/local/bin/dagger-engine'])
  for path in blobs:capture(['docker','cp',path,name+':/usr/local/share/dagger/content/blobs/sha256/'+Path(path).name])
  prepared['containers'].append({'name':name,'variant':variant,'port':port})
  (dest/'prepared.json').write_text(json.dumps(prepared,indent=2)+'\n')
 print(json.dumps({'prepared':str(dest),'containers':len(prepared['containers']),'started':False}),flush=True)

def summarize(row,path,variant):
 samples=json.loads((path/'samples.json').read_text());first,last=samples[0],samples[-1]
 row.update(variant=variant,engine_write_mib=sum(v.get('wbytes',0) for v in row['engine_io'].values())/2**20,
  dirty_start_mib=first['meminfo_kib']['Dirty']/1024,dirty_end_mib=last['meminfo_kib']['Dirty']/1024,
  writeback_start_mib=first['meminfo_kib']['Writeback']/1024,writeback_end_mib=last['meminfo_kib']['Writeback']/1024,
  sampled_peak_engine_memory_mib=max(s['engine_memory'] for s in samples)/2**20)
 if 'nvme0n1' in first['diskstats']:
  a,b=first['diskstats']['nvme0n1'],last['diskstats']['nvme0n1'];writes=b[4]-a[4]
  row.update(device_write_mib=(b[6]-a[6])*512/2**20,device_mean_write_await_ms=(b[7]-a[7])/writes if writes else 0,device_busy_s=(b[9]-a[9])/1000)
 (path/'summary.json').write_text(json.dumps(row,indent=2)+'\n');return row

def benchmark(dest):
 prepared=json.loads((dest/'prepared.json').read_text());assert prepared['order'] in [ORDER,['control','static']] and len(prepared['containers'])==len(prepared['order'])
 for path,want in prepared['input_sha256'].items():assert digest(path)==want,path+' changed since preparation'
 for path,want in prepared['binaries'].values():assert digest(path)==want,path+' binary changed'
 lab.B=dest
 for key in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','_EXPERIMENTAL_DAGGER_CACHE_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG']:lab.ENV.pop(key,None)
 lab.ENV['DAGGER_CLOUD_URL']='https://api.dagger.cloud'
 rows=[]
 for item in prepared['containers']:
  name,port=item['name'],item['port']
  state=json.loads(capture(['docker','inspect','--format','{{json .State}}',name]));assert state['Status']=='created','cold container was already started'
  try:
   started=time.monotonic();capture(['docker','start',name])
   for _ in range(300):
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
    except OSError:time.sleep(.1)
   else:raise RuntimeError('engine not ready')
   ready=time.monotonic()-started
   for label in ['cold','warm-0']:
    row=lab.measure(name,port,WORKSPACE,label,profile=False)
    row['engine_start_to_ready_seconds']=ready
    rows.append(summarize(row,dest/name/label,item['variant']))
    (dest/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
  finally:
   stopped=subprocess.run(['docker','stop','--timeout','30',name],capture_output=True,text=True)
   print(json.dumps({'stopped':name,'status':stopped.returncode}),flush=True)
   for path,want in prepared['input_sha256'].items():assert digest(path)==want,path+' changed during benchmark'

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','benchmark']);parser.add_argument('--prefix',default='cold-ts-static-abba');parser.add_argument('--first-port',type=int,default=6250);parser.add_argument('--order',choices=['ABBA','AB'],default='ABBA');args=parser.parse_args()
 if '/' in args.prefix or args.prefix in ['.','..']:raise SystemExit('invalid task prefix')
 dest=HERE/args.prefix
 if args.action=='prepare':prepare(dest,args.first_port,ORDER if args.order=='ABBA' else ['control','static'])
 else:benchmark(dest)
