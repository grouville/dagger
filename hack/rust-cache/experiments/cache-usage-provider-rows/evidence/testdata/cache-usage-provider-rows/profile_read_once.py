from pathlib import Path
import json,os,subprocess,time
from bench_engine import BenchEngine
family=Path(__file__).parent
root=family/'read-once-provider-profiles';root.mkdir(exist_ok=False)
engine=BenchEngine(root)
rows=[]
for arm,binary in [('before','provider-dense-before.test'),('after','read-once-after.test')]:
    engine.idle(arm)
    command=[str(family/binary),'-test.run=^$','-test.bench=^BenchmarkCachePruneProviderDense$','-test.benchtime=1x','-test.count=1','-test.cpuprofile='+str(root/(arm+'.pprof'))]
    started=time.monotonic()
    with (root/(arm+'.log')).open('w') as out:r=subprocess.run(command,env=dict(os.environ,GOMAXPROCS='8'),cwd='/tmp/dagger-cache-usage-sampler-only',stdout=out,stderr=subprocess.STDOUT)
    rows.append(dict(arm=arm,command=command,seconds=time.monotonic()-started,exit_code=r.returncode))
    (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(arm,r.returncode,flush=True)
    assert r.returncode==0
