import json, pathlib
base=pathlib.Path('/tmp/collections-perf/tar-parent-cache')
summary=[]
for mode in ['isolated','full','balanced']:
 path=base/mode/'summary.json'
 if not path.exists():continue
 for row in json.loads(path.read_text()):
  p=base/mode/row['variant']
  raw=[json.loads(s) for s in (p/'host-samples.jsonl').read_text().splitlines()]
  a,b=raw[0],raw[-1]
  def ticks(r):return list(map(int,r['stat'].splitlines()[0].split()[1:9]))
  delta=[y-x for x,y in zip(ticks(a),ticks(b))]
  def psi(r,name):return {s.split()[0]:int(s.split('total=')[1]) for s in r['pressure/'+name].splitlines()}
  with (p/'runs.wcprof').open() as f:
   h=json.loads(next(f));strings=h['strings'];events=[json.loads(s) for s in f]
  row.update(mode=mode,host_iowait_percent=100*delta[4]/sum(delta),host_full_io_stall_seconds=(psi(b,'io')['full']-psi(a,'io')['full'])/1e6,open_ops=sum(1 for x in events if x.get('e')=='op' and not x.get('d')))
  timeline=[]
  for ev in sorted(events,key=lambda x:x.get('s',0)):
   cls=strings[ev.get('c',0)];duration=(ev.get('d',0)-ev.get('s',0))/1e9
   if cls.startswith('builtinImage.') or (cls=='exec.processRun' and duration>.5) or (cls=='Container.from' and ev.get('k')=='call_exec' and duration>.5):
    timeline.append({'class':cls,'kind':ev.get('k'),'start_seconds':ev.get('s',0)/1e9,'seconds':duration,'argv':strings[ev.get('m',0)],'ident':strings[ev.get('i',0)]})
  (p/'timeline.json').write_text(json.dumps(timeline,indent=2)+'\n')
  compact=[]
  for r in raw:
   def numbers(name):return {s[0].rstrip(':'):int(s[1]) for s in map(str.split,r[name].splitlines()) if len(s)>1}
   vm=numbers('vmstat');mem=numbers('meminfo')
   compact.append({'time_ns':r['time_ns'],'monotonic_ns':r['monotonic_ns'],'cpu_ticks':ticks(r),'pressure_total_us':{k:psi(r,k) for k in ['cpu','io','memory']},'vmstat':{k:vm[k] for k in ['pswpin','pswpout','pgmajfault','nr_dirty','nr_writeback','nr_written']},'meminfo_kib':{k:mem[k] for k in ['MemAvailable','SwapFree','Dirty','Writeback']},'diskstats':{s[2]:list(map(int,s[3:])) for s in map(str.split,r['diskstats'].splitlines()) if s[2]=='nvme0n1'}})
  (p/'host-compact.json').write_text(json.dumps(compact,separators=(',',':'))+'\n')
  summary.append(row)
(base/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for r in summary:print(r['mode'],r['variant'],f"wall={r['seconds']:.3f} import={r['go_import_seconds']:.3f} iowait={r['host_iowait_percent']:.2f}% io_stall={r['host_full_io_stall_seconds']:.3f} open={r['open_ops']}")
