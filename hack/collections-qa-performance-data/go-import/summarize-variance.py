"""Summarize saved wcprof and host samples (Linux, measured page size 4096)."""
import json
from pathlib import Path
base=Path('/tmp/collections-perf/go-import')
def numbers(text):
    return {s[0].rstrip(':'):int(s[1]) for s in map(str.split,text.splitlines()) if len(s)>1}
def pressures(row, name):
    return {line.split()[0]:int(line.rsplit('=',1)[1]) for line in row['pressure/'+name].splitlines()}
for path in sorted((base/'variance').glob('quiet-*')):
    samples=[json.loads(line) for line in (path/'host-samples.jsonl').read_text().splitlines()]
    compact=[]
    for row in samples:
        vm=numbers(row['vmstat']);mem=numbers(row['meminfo'])
        compact.append({
            'time_ns':row['time_ns'],'monotonic_ns':row['monotonic_ns'],'load':row['load'],
            'cpu_ticks':list(map(int,row['stat'].splitlines()[0].split()[1:9])),
            'vmstat':{k:vm[k] for k in ['pswpin','pswpout','pgmajfault','nr_dirty','nr_writeback','nr_written']},
            'meminfo_kib':{k:mem[k] for k in ['MemAvailable','SwapFree','Dirty','Writeback']},
            'pressure_total_us':{k:pressures(row,k) for k in ['cpu','io','memory']},
            'cpu_frequency_khz':row['cpu_frequency_khz'],
            'diskstats':{s[2]:list(map(int,s[3:])) for s in map(str.split,row['diskstats'].splitlines()) if s[2]=='nvme0n1'},
        })
    (path/'host-compact.json').write_text(json.dumps({'page_bytes':4096,'samples':compact},separators=(',',':'))+'\n')
for kind,names in [('compare',['control-0','control-1']),('variance',['quiet-0','quiet-1','quiet-2'])]:
    for name in names:
        path=base/kind/name
        with (path/'runs.wcprof').open() as f:
            header=json.loads(next(f));strings=header['strings'];events=[json.loads(line) for line in f]
        timeline=[]
        for ev in sorted(events,key=lambda x:x.get('s',0)):
            cls=strings[ev.get('c',0)];duration=(ev.get('d',0)-ev.get('s',0))/1e9
            if cls.startswith('builtinImage.') or (cls=='exec.processRun' and duration>.5) or (cls in ['Container.from','Host.directory'] and ev.get('k')=='call_exec' and duration>.5):
                timeline.append({'class':cls,'kind':ev.get('k'),'start_seconds':ev.get('s',0)/1e9,'seconds':duration,'argv':strings[ev.get('m',0)],'ident':strings[ev.get('i',0)]})
        (path/'timeline.json').write_text(json.dumps({'epoch_unix_nano':header['epoch_unix_nano'],'operations':timeline},indent=2)+'\n')
        print(name, 'dropped', header['dropped_events'], 'open',sum(1 for e in events if e.get('e')=='op' and not e.get('d')))
