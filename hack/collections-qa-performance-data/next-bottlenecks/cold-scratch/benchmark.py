#!/usr/bin/env python3
"""Run only after prepare.py and an exclusive benchmark window are complete."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
BASE = Path('/tmp/collections-perf/post-rebase-io')
sys.path.insert(0, str(BASE))
import run as lab

WORKSPACE = Path('/tmp/collections-perf/normal-baseline/greetings-split')
IMAGES = {
    'baseline512': 'localhost/dagger-engine.collections-main-io:candidate',
    'scratch': 'localhost/dagger-engine.collections-main-io:scratch-audit',
}
# Add RAM/OOM observations without per-process enumeration or filesystem walks.
original_sample = lab.sample
def sample(cg):
    row = original_sample(cg)
    row['engine_memory_stat'] = {k:v for k,v in lab.fields(cg/'memory.stat').items()
        if k in ('anon','file','shmem','file_dirty','file_writeback','swapcached')}
    row['engine_memory_events'] = lab.fields(cg/'memory.events')
    return row
lab.sample = sample

def summarize(row, dest, variant):
    samples = json.loads((dest/'samples.json').read_text())
    first,last = samples[0],samples[-1]
    row['variant'] = variant
    row['sampled_peak_engine_memory_mib'] = max(r['engine_memory'] for r in samples)/2**20
    row['sampled_peak_engine_shmem_mib'] = max(r['engine_memory_stat']['shmem'] for r in samples)/2**20
    row['sampled_peak_engine_anon_mib'] = max(r['engine_memory_stat']['anon'] for r in samples)/2**20
    row['engine_memory_events_delta'] = {k:v-first['engine_memory_events'].get(k,0)
        for k,v in last['engine_memory_events'].items()}
    row['engine_write_mib'] = sum(d.get('wbytes',0) for d in row['engine_io'].values())/2**20
    row['dirty_start_mib'] = first['meminfo_kib']['Dirty']/1024
    row['writeback_start_mib'] = first['meminfo_kib']['Writeback']/1024
    row['dirty_peak_mib'] = max(r['meminfo_kib']['Dirty'] for r in samples)/1024
    row['dirty_end_mib'] = last['meminfo_kib']['Dirty']/1024
    a,b = first['diskstats']['nvme0n1'],last['diskstats']['nvme0n1']
    writes=b[4]-a[4]
    row['device_write_mib'] = (b[6]-a[6])*512/2**20
    row['device_mean_write_await_ms'] = (b[7]-a[7])/writes if writes else 0
    row['device_busy_s'] = (b[9]-a[9])/1000
    (dest/'summary.json').write_text(json.dumps(row,indent=2)+'\n')
    return row

parser=argparse.ArgumentParser()
parser.add_argument('--prefix',default='cold-scratch-abba')
parser.add_argument('--first-port',type=int,default=6190)
parser.add_argument('--profile-cold',action='store_true',help='Separate diagnostic invocation only; primary comparison leaves this off.')
args=parser.parse_args()
lab.B = BASE/'cold-scratch-audit'/args.prefix
lab.B.mkdir(exist_ok=False)
# Input and executable identity are held fixed; no source modifications are made.
input_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
    WORKSPACE/'main_test.go',lab.CLI,Path(__file__)]}
provenance={'images':{},'input_sha256':input_hashes,'timing':'ready engine, empty local Dagger volume; full new CLI process through exit; host page cache preserved',
    'profile_cold':args.profile_cold,'sequence':['baseline512','scratch','scratch','baseline512']}
for variant,image in IMAGES.items():
    provenance['images'][variant] = lab.run(['docker','image','inspect','--format','{{.Id}}',image])
(lab.B/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
rows=[]
for i,variant in enumerate(provenance['sequence']):
    name=f'dagger-engine.collections-{args.prefix}-{i}'
    port=args.first_port+i
    try:
        lab.start(name,port,image=IMAGES[variant])
        for label,profile in [('cold',args.profile_cold),('warm-0',False),('warm-1',False)]:
            row=lab.measure(name,port,WORKSPACE,label,profile=profile)
            rows.append(summarize(row,lab.B/name/label,variant))
            (lab.B/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    finally:
        stopped=subprocess.run(['docker','stop','--timeout','30',name],capture_output=True,text=True)
        print(json.dumps({'stopped':name,'status':stopped.returncode}),flush=True)
        for path,wanted in input_hashes.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==wanted,path+' changed during benchmark'
