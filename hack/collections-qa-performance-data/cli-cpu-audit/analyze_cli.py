"""Aggregate saved profiles only; never reads raw telemetry or launches a CLI."""
from pathlib import Path
import hashlib,json,re,subprocess
P=Path(__file__).resolve().parent;O=P/'analysis';GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
def duration(s):
 m=re.fullmatch(r'([0-9.]+)(ns|us|µs|ms|s)?',s);assert m,s
 return float(m[1])*{None:1,'ns':.000001,'us':.001,'µs':.001,'ms':1,'s':1000}[m[2]]
def parse(text):
 nodes=[]
 for line in text.splitlines():
  m=re.match(r'^\s*(\S+)\s+[\d.]+%\s+[\d.]+%\s+(\S+)\s+[\d.]+%\s+(.+)$',line)
  if m:nodes.append({'function':m[3],'flat_ms':duration(m[1]),'cumulative_ms':duration(m[2])})
 return nodes
def top(profile):
 r=subprocess.run([GO,'tool','pprof','-top','-nodecount=0','-nodefraction=0','-unit=ms',str(profile)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30);assert r.returncode==0,r.stderr
 return r.stdout
fields={'source_walk':'github.com/dagger/dagger/internal/fsutil.(*sender).walk','readdir':'os.ReadDir','filepath_rel':'path/filepath.Rel','metadata_decode':'github.com/dagger/dagger/internal/cmd/dagger.(*moduleDef).loadTypeDefs','telemetry_consume':'github.com/dagger/dagger/engine/client.consumeTelemetryPayload','telemetry_unmarshal':'github.com/dagger/dagger/engine/client.unmarshalLiveTelemetry','frontend_dispatch':'github.com/dagger/dagger/dagql/idtui.(*frontendPretty).dispatch','gc_workers':'runtime.gcBgMarkWorker','labels':'github.com/dagger/dagger/engine/telemetry.LoadDefaultLabels'}
rows=json.loads((P/'local-v1/results.json').read_text());result=[]
for idx,row in enumerate(rows):
 if row['kind']!='cpu':continue
 name=f'{idx:02d}-{row["flow"]}-cpu';profile=P/'local-v1'/name/'cli.pprof';text=top(profile);nodes=parse(text);lookup={r['function']:r for r in nodes}
 m=re.search(r'Duration: ([\d.]+\w+), Total samples = ([\d.]+\w+)',text);assert m
 prof_ms=duration(m[1]);cpu=duration(m[2]);tree=1000*(row['process_tree_user_seconds']+row['process_tree_system_seconds'])
 item={'capture':name,'flow':row['flow'],'profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),'sampled_dagger_cpu_ms':cpu,'profile_duration_ms_rounded':prof_ms,'instrumented_cli_ms':row['seconds_instrumented']*1000,'waited_process_tree_cpu_ms':tree,'tree_cpu_minus_sampled_cpu_ms_unattributed':tree-cpu,'outside_profile_wall_ms_rounded_upper_envelope':row['seconds_instrumented']*1000-prof_ms,'anchors_cumulative_ms_nonadditive':{k:lookup.get(fn,{}).get('cumulative_ms',0)for k,fn in fields.items()},'top_flat':sorted(nodes,key=lambda r:(-r['flat_ms'],r['function']))[:15],'top_cumulative':sorted(nodes,key=lambda r:(-r['cumulative_ms'],r['function']))[:25]}
 item['trace_profiles']={}
 for kind in ['sync','syscall','sched','net']:
  traceprof=O/(name+'-'+kind+'.pprof.private')
  if not traceprof.exists():continue
  trace_nodes=parse(top(traceprof));look={r['function']:r for r in trace_nodes}
  relevant=['github.com/dagger/dagger/engine/client/drivers.containerRuntimeAvailable','github.com/dagger/dagger/engine/client.newBuildkitClient','runtime/pprof.StopCPUProfile','github.com/dagger/dagger/internal/fsutil.(*sender).walk','os.Lstat','os.Stat','golang.org/x/sys/unix.Llistxattr','syscall.Getdents','runtime.(*profBuf).read']
  item['trace_profiles'][kind]={'anchors_cumulative_ms_nonadditive':{fn:look.get(fn,{}).get('cumulative_ms',0)for fn in relevant},'top_flat':sorted(trace_nodes,key=lambda r:(-r['flat_ms'],r['function']))[:10]}
 result.append(item)
out={'scope':'Seven saved CLI CPU captures and four saved runtime traces; local-only. CPU samples are not wall time; cumulative anchors overlap; trace delays aggregate goroutines. No ordinary speed or attribution of unprofiled CPU is implied.','source_head':'85b60f7a0a16a27459ef571bc94bcf870c876dcc','cli_sha256':'748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30','engine_sha256':'9912b76324d1015e6811ea3a8ac7bdfb029ce6c079226c9a3b7aa6de8a3212a5','restoration':json.loads((P/'local-v1/restoration.json').read_text()),'captures':result}
(O/'numeric-cli-evidence.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps([{'capture':r['capture'],'cpu_ms':r['sampled_dagger_cpu_ms'],'tree_ms':round(r['waited_process_tree_cpu_ms'],3),'outside_profile_wall_ms':round(r['outside_profile_wall_ms_rounded_upper_envelope'],3)}for r in result]))
