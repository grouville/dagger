from pathlib import Path
import json,statistics,collections
B=Path('/tmp/collections-perf/post-rebase-io')
rows=[]
for d in sorted(B.glob('dagger-engine.collections-disk-abba-*')):
 for p in sorted(d.glob('*/result.json')):
  r=json.loads(p.read_text());samples=json.loads((p.parent/'samples.json').read_text());a,z=samples[0],samples[-1]
  var='baseline' if d.name.endswith(('0','3')) else 'candidate'
  r.update(variant=var,dirty_start_mib=a['meminfo_kib']['Dirty']/1024,dirty_peak_mib=max(s['meminfo_kib']['Dirty'] for s in samples)/1024,dirty_end_mib=z['meminfo_kib']['Dirty']/1024)
  io=r['engine_io'].get('259:1',{});r['engine_write_mib']=io.get('wbytes',0)/1048576;r['engine_read_mib']=io.get('rbytes',0)/1048576
  disk1=a['diskstats']['nvme0n1'];disk2=z['diskstats']['nvme0n1'];delta=[y-x for x,y in zip(disk1,disk2)]
  r['device_write_mib']=delta[6]/2048;r['device_write_await_ms']=delta[7]/max(delta[4],1);r['device_busy_seconds']=delta[9]/1000
  r['device_read_mib']=delta[2]/2048
  r['sampled_system_cgroup_write_mib']=sum(max(0,b.get('259:1',{}).get('wbytes',0)-a['system_io'].get(cg,{}).get('259:1',{}).get('wbytes',0)) for cg,b in z['system_io'].items())/1048576
  r['cpu_pressure_some_s']=(z['host_psi']['cpu']['some']-a['host_psi']['cpu']['some'])/1e6
  r['memory_pressure_full_s']=(z['host_psi']['memory']['full']-a['host_psi']['memory']['full'])/1e6
  rows.append(r)
(B/'abba-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:
 print(r['variant'],r['label'],round(r['seconds'],3),'host/engine IO',round(r['host_io_full_seconds'],3),round(r['engine_io_full_seconds'],3),'writes MiB',round(r['engine_write_mib']),'dirty peak',round(r['dirty_peak_mib']),'device await ms',round(r['device_write_await_ms'],1))
for var in ['baseline','candidate']:
 v=[r['seconds'] for r in rows if r['variant']==var and r['label'].startswith('warm-') and r['label']!='warm-profile']
 if v: print(var,'warm median',statistics.median(v),'n',len(v))
