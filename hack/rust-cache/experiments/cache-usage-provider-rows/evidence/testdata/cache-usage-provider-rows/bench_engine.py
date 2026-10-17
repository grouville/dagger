from pathlib import Path
import json
import subprocess
import time
import urllib.request

class BenchEngine:
    def __init__(self, output):
        self.output = output
        self.debug = 'http://127.0.0.1:16104/debug/'
        self.record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
        path = Path(f"/proc/{self.record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
        self.cgroup = Path('/sys/fs/cgroup')/path

    def get(self, route, data=None, timeout=30):
        with urllib.request.urlopen(urllib.request.Request(self.debug+route, data=data), timeout=timeout) as response:
            return json.load(response)

    def mode(self, route, enabled):
        assert self.get(route+'?enabled='+str(enabled).lower(), b'')['enabled'] == enabled

    def pressure(self):
        result = {}
        for name, path in [('host', Path('/proc/pressure')), ('engine', self.cgroup)]:
            for kind in ['cpu', 'io', 'memory']:
                filename = path/(kind if name == 'host' else kind+'.pressure')
                for line in filename.read_text().splitlines():
                    result[name+'.'+kind+'.'+line.split()[0]] = int(line.split('total=')[1])
        return result

    def cpu(self):
        return int(next(line.split()[1] for line in (self.cgroup/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec ')))/1e6

    def idle(self, label):
        started = time.monotonic()
        while True:
            before = self.pressure(); before_cpu = self.cpu(); mark = time.monotonic(); time.sleep(1)
            elapsed = time.monotonic()-mark; after = self.pressure(); state = self.get('client-lifecycle')
            quiet = not state.get('sessions') and state['active_requests'] == 0 and (after['host.io.some']-before['host.io.some'])/(elapsed*1e6)<.05 and (self.cpu()-before_cpu)/elapsed<.15
            with (self.output/'admission.jsonl').open('a') as out:
                out.write(json.dumps(dict(label=label, seconds=time.monotonic()-started, admitted=quiet))+'\n')
            if quiet:
                return
            assert time.monotonic()-started<120, 'admission timeout'
