import json,subprocess,time,urllib.request
from pathlib import Path

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'parallel-fingerprint'
record=json.loads(subprocess.check_output(['docker','inspect','dagger-rust-parser-state-pool-oct14']))[0]
assert record['State']['Running']
engine=Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':',2)[2].strip().lstrip('/')
def pressure():
    values={}
    for prefix,path in [('host',Path('/proc/pressure')),('engine',engine)]:
        for kind in ['cpu','io','memory']:
            for line in (path/(kind if prefix=='host' else kind+'.pressure')).read_text().splitlines():
                values[prefix+'.'+kind+'.'+line.split()[0]]=int(line.split('total=')[1])
    return values
def cpu():
    return next(int(line.split()[1]) for line in (engine/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec '))
started=time.monotonic();last_report=-10;consecutive=0
with (root/'post-restart-admission.jsonl').open('w') as out:
    while True:
        before=pressure();before_cpu=cpu();tick=time.monotonic();time.sleep(1)
        elapsed=time.monotonic()-tick;after=pressure()
        stalls={k:(after[k]-before[k])/(elapsed*1e6) for k in before}
        cpu_rate=(cpu()-before_cpu)/(elapsed*1e6)
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle',timeout=10) as response:state=json.load(response)
        admitted=not state.get('sessions') and state['active_requests']==0 and stalls['host.io.some']<.05 and stalls['engine.io.some']<.01 and stalls['host.cpu.some']<.10 and cpu_rate<.10
        consecutive=consecutive+1 if admitted else 0
        seconds=time.monotonic()-started
        out.write(json.dumps(dict(seconds=seconds,admitted=admitted,consecutive=consecutive,stall_fraction=stalls,engine_cpu_rate=cpu_rate))+'\n');out.flush()
        if seconds-last_report>=10:
            print('Waiting for quiet',round(seconds),'seconds; host IO',round(stalls['host.io.some']*100,1),'engine IO',round(stalls['engine.io.some']*100,1),'percent',flush=True)
            last_report=seconds
        if consecutive>=3:break
        assert seconds<600,'Still running but no quiet admission window; retain evidence and inspect, do not restart the engine.'
print('Quiet admission confirmed; launching unchanged measurement driver',flush=True)
command=['python3',str(root/'measure_commands.py'),'--output-root',str(root/'commands'),'--pairs','8']
with (root/'commands-driver.log').open('w') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
raise SystemExit(result.returncode)
