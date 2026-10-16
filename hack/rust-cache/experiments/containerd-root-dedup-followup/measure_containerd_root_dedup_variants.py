from pathlib import Path
import hashlib,json,os,re,statistics,subprocess,time,urllib.request

base=Path('/tmp/rust-cache-sipsma-review/containerd-mark-graph')
root=base/'variants'
output=root/'paired'
output.mkdir(exist_ok=False)
arms={
 'before': {'metadata':base/'metadata-before.test','gc':base/'gc-before.test','source':base/'gc-before.go'},
 'membership': {'metadata':base/'metadata-after.test','gc':base/'gc-after.test','source':base/'production-gc.go'},
 'assign-length': {'metadata':root/'metadata-assign-length.test','gc':root/'gc-assign-length.test','source':root/'assign-length.go'},
 'map-keys': {'metadata':root/'metadata-map-keys.test','gc':root/'gc-map-keys.test','source':root/'map-keys.go'},
}
orders=[['before','membership','map-keys','assign-length'],['membership','assign-length','before','map-keys'],['assign-length','map-keys','membership','before'],['map-keys','before','assign-length','membership']]
def write(name,value):(output/name).write_text(json.dumps(value,indent=2)+'\n')
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
def admit(label):
 started=time.monotonic()
 while True:
  before=pressure();now=time.monotonic();time.sleep(1);elapsed=time.monotonic()-now;after=pressure()
  fractions={k:(after[k]-before[k])/(elapsed*1e6) for k in before}
  with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle',timeout=10) as response:state=json.load(response)
  accepted=not state.get('sessions') and state['active_requests']==0 and fractions['io.some']<.02
  with (output/'admission.jsonl').open('a') as stream:stream.write(json.dumps(dict(label=label,admitted=accepted,stall_fraction=fractions))+'\n')
  if accepted:return
  assert time.monotonic()-started<90,'admission timeout; preserve completed observations'
with (base/'containerdmeta.db').open('rb') as stream:database_sha=hashlib.file_digest(stream,'sha256').hexdigest()
write('metadata.json',dict(pairs=8,toolchain='go1.26.6',gomaxprocs=8,database_sha256=database_sha,graph=json.loads((base/'graph-statistics.json').read_text()),scope='Read-only real metadata mark with independent graph oracle; unique-root controls; fixture loading excluded; no end-to-end claim.',sources={name:{'gc_sha256':hashlib.sha256(arm['source'].read_bytes()).hexdigest(), 'binary_sha256':{k:hashlib.sha256(arm[k].read_bytes()).hexdigest() for k in ['metadata','gc']}} for name,arm in arms.items()},orders=orders))
env=dict(os.environ,GOMAXPROCS='8',DAGGER_GC_GRAPH_ROOT=str(base))
pattern=re.compile(r'^(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op(?:\s+([\d.]+) retained)?\s+(\d+) B/op\s+(\d+) allocs/op$',re.M)
rows=[]
for pair in range(8):
 for name in orders[pair%4]:
  label=str(pair)+'-'+name;admit(label);before=pressure();started=time.monotonic();benchmarks={}
  for package,benchmark,duration,count in [('metadata','^BenchmarkDaggerRetainedMark$','1x',1),('gc','^BenchmarkTricolorUniqueRoots$','150ms',2)]:
   logfile=output/(label+'-'+package+'.log')
   with logfile.open('w') as stream:result=subprocess.run([str(arms[name][package]),'-test.run=^$','-test.bench='+benchmark,'-test.benchtime='+duration,'-test.count=1'],env=env,stdout=stream,stderr=subprocess.STDOUT)
   matches=pattern.findall(logfile.read_text());assert result.returncode==0 and len(matches)==count,(label,package,result.returncode,matches)
   for bench,n,ns,retained,allocated,allocations in matches:
    if retained:assert int(float(retained))==77772
    benchmarks[bench]=dict(iterations=int(n),ns_per_op=float(ns),bytes_per_op=int(allocated),allocations_per_op=int(allocations),retained=int(float(retained)) if retained else None)
  elapsed=time.monotonic()-started;after=pressure()
  rows.append(dict(pair=pair,arm=name,process_seconds=elapsed,benchmarks=benchmarks,stall_fraction={k:(after[k]-before[k])/(elapsed*1e6) for k in before}))
  write('runs.json',rows)
  print(label,json.dumps(benchmarks),flush=True)
summary={}
for bench in rows[0]['benchmarks']:
 summary[bench]={}
 for name in arms:
  values=[r['benchmarks'][bench] for r in rows if r['arm']==name]
  baseline=[r['benchmarks'][bench] for r in rows if r['arm']=='before']
  savings=[a['ns_per_op']-b['ns_per_op'] for a,b in zip(baseline,values)]
  summary[bench][name]={metric:statistics.median(v[metric] for v in values) for metric in ['ns_per_op','bytes_per_op','allocations_per_op']}
  summary[bench][name].update(median_paired_saving_ns=statistics.median(savings),faster_pairs=sum(v>0 for v in savings))
with (base/'containerdmeta.db').open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==database_sha,'database copy changed'
write('summary.json',summary)
print(json.dumps(summary,indent=2),flush=True)
