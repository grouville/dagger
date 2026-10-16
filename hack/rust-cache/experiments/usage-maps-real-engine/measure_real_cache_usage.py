import argparse
import json
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('--pairs',type=int,default=8)
parser.add_argument('--reverse-order',action='store_true')
parser.add_argument('--output-root',required=True,type=Path)
args=parser.parse_args()
root=args.output_root
root.mkdir(exist_ok=False)
base='http://127.0.0.1:16104/debug/'
record=json.loads(subprocess.check_output(['docker','inspect','dagger-rust-parser-state-pool-oct14']))[0]
engine=Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':',2)[2].strip().lstrip('/')
parent=engine.parent

def cpu(group):
    return int(dict(line.split() for line in (group/'cpu.stat').read_text().splitlines())['usage_usec'])/1e6

def pressure():
    result={}
    for prefix,directory in [('host',Path('/proc/pressure')),('engine',engine)]:
        for kind in ['cpu','io','memory']:
            p=directory/(kind if prefix=='host' else kind+'.pressure')
            for line in p.read_text().splitlines():
                result[prefix+'.'+kind+'.'+line.split()[0]]=int(line.split('total=')[1])
    return result

def get(route):
    with urllib.request.urlopen(base+route,timeout=10) as response:
        return json.load(response)

def admit(label):
    start=time.monotonic()
    while True:
        before=pressure();t=time.monotonic();time.sleep(1);elapsed=time.monotonic()-t
        after=pressure();state=get('client-lifecycle')
        ratios={key:(after[key]-before[key])/(elapsed*1e6) for key in before}
        idle=not state.get('sessions') and state['active_requests']==0
        admitted=idle and ratios['host.io.some']<.05 and ratios['engine.io.some']<.01
        with (root/'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label,elapsed=time.monotonic()-start,window=elapsed,stall_fraction=ratios,idle=idle,admitted=admitted))+'\n')
        if admitted:return
        assert time.monotonic()-start<60,'quiet admission timeout'

rows=[]
assert not get('wcprof/enabled')['global_enabled']
(root/'metadata.json').write_text(json.dumps(dict(engine_id=record['Id'],engine_started=record['State']['StartedAt'],
    operation='measurePruneState only; no planning or eviction',scope='real retained owned engine cache',
    paired_modes_in_same_engine_process=True,reverse_order=args.reverse_order,default_mode=False,process_allocation_counters=True,
    profiler_enabled=False,post_launch_stalls_excluded=False,cpu_paths={'engine':str(engine),'docker_total':str(parent)},
    compiler_workloads=False,engine_restarted_between_variants=False,source='usage-maps-real-engine/overlay.json'),indent=2)+'\n')
for pair in range(-2,args.pairs):
    modes=['before','after'] if (pair+int(args.reverse_order))%2==0 else ['after','before']
    for mode in modes:
        label=f'{pair}-{mode}';admit(label)
        before=pressure();cpu_before={k:cpu(v) for k,v in [('engine',engine),('docker_total',parent)]}
        request=urllib.request.Request(base+'cache-usage-measurement?enabled='+str(mode=='after').lower(),data=b'',method='POST')
        start=time.monotonic()
        with urllib.request.urlopen(request,timeout=180) as response:
            result=json.load(response)
        elapsed=time.monotonic()-start
        cpu_after={k:cpu(v) for k,v in [('engine',engine),('docker_total',parent)]};after=pressure()
        assert result['complete'] and result['enabled']==(mode=='after'),result
        row=dict(pair=pair,mode=mode,label=label,prepared=pair<0,request_seconds=elapsed,**result,
                 cpu_seconds={k:cpu_after[k]-cpu_before[k] for k in cpu_before},
                 stall_fraction={k:(after[k]-before[k])/(elapsed*1e6) for k in before})
        rows.append(row)
        (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps({key:row[key] for key in ['pair','mode','rows','used_bytes','seconds','allocated_bytes','allocations','cpu_seconds','go_gc_cycles']}),flush=True)
values=[r for r in rows if r['pair']>=0]
assert len({r['rows'] for r in values})==1,'cache result population changed; keep raw observations'
assert len({r['used_bytes'] for r in values})==1,'cache byte accounting changed; keep raw observations'
summary={}
for key in ['seconds','request_seconds','allocated_bytes','allocations']:
    medians={mode:statistics.median(r[key] for r in values if r['mode']==mode) for mode in ['before','after']}
    pairs={pair:{r['mode']:r[key] for r in values if r['pair']==pair} for pair in range(args.pairs)}
    summary[key]=dict(medians=medians,median_paired_saving=statistics.median(v['before']-v['after'] for v in pairs.values()),faster_pairs=sum(v['after']<v['before'] for v in pairs.values()))
summary['rows']=values[0]['rows'];summary['used_bytes']=values[0]['used_bytes']
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
