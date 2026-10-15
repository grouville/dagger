import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'scalar-array-restore-components'
root.mkdir(exist_ok=False)
binaries = {side:base/('scalar-array-restore-'+side+'.test') for side in ['main','new']}
metadata = dict(repetitions=5, Go='1.26.6', GOMAXPROCS=8, unchanged_main='a5c17bb7e',
    fixture='N builtin String items; the producer call also contains N literal path arguments',
    scope='DefaultPersistedSelfCodec.DecodeResult; not a complete cache constructor or Rust command',
    binary_sha256={side:hashlib.sha256(path.read_bytes()).hexdigest() for side,path in binaries.items()},
    no_parallel_build_or_profile=True, post_sample_exclusion=False)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')

def pressure():
    return {kind:int(Path('/proc/pressure/'+kind).read_text().splitlines()[0].split('total=')[1]) for kind in ['cpu','io','memory']}

def idle(label):
    started=time.monotonic()
    while True:
        before=pressure();t=time.monotonic();time.sleep(1);elapsed=time.monotonic()-t;after=pressure()
        fractions={kind:(after[kind]-before[kind])/(elapsed*1e6) for kind in before}
        admitted=fractions['cpu']<.10 and fractions['io']<.05
        with (root/'admission.jsonl').open('a') as stream:stream.write(json.dumps(dict(label=label,stall_fraction=fractions,admitted=admitted))+'\n')
        if admitted:return
        assert time.monotonic()-started<60,'quiet admission timed out'

rows=[]
for pair in range(5):
    for side in (['main','new'] if pair%2==0 else ['new','main']):
        label=f'{pair}-{side}';idle(label)
        command=[str(binaries[side]),'-test.run=^$','-test.bench=^BenchmarkPersistedScalarArrayRestore$','-test.benchmem','-test.benchtime=300ms','-test.cpu=8']
        with (root/(label+'.log')).open('w') as output:result=subprocess.run(command,env=dict(os.environ,GOMAXPROCS='8'),stdout=output,stderr=subprocess.STDOUT)
        assert not result.returncode,label
        parsed=[]
        for line in (root/(label+'.log')).read_text().splitlines():
            match=re.match(r'BenchmarkPersistedScalarArrayRestore/(\d+)-\d+\s+\d+\s+(\d+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
            if match:
                size,ns,byte,alloc=map(int,match.groups());parsed.append(size)
                rows.append(dict(pair=pair,side=side,size=size,nanoseconds=ns,bytes=byte,allocations=alloc))
        assert sorted(parsed)==[128,512,1024],(label,parsed)
        (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
        print('PASS',label,flush=True)
summary={str(size):{side:{key:statistics.median(row[key] for row in rows if row['size']==size and row['side']==side) for key in ['nanoseconds','bytes','allocations']} for side in binaries} for size in [128,512,1024]}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
