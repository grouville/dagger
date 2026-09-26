"""Diagnose a genuinely new source edit; no pre-listing or pre-execution."""
from pathlib import Path
import hashlib,json,os,re,signal,subprocess,threading,time
import experiment as x

lab=Path(__file__).resolve().parent
manifest=json.loads((lab/'prepared.json').read_text())
assert (lab/'local-v1/summary.json').exists(),'finish the exclusive timing series first'
out=lab/'fresh-edit-profiles-v1';out.mkdir(mode=0o700,exist_ok=False)
item=manifest['containers']['combined'];assert x.owned(item)['State']['Running']
assert x.capture(['docker','exec',item['name'],'sha256sum','/usr/local/bin/dagger-engine']).split()[0]==item['sha256']
app=lab/'greetings';original=(app/'main.go').read_bytes()
assert hashlib.sha256(original).hexdigest()==manifest['source_hashes']['main.go']
env={k:os.environ[k] for k in ('PATH','HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
env.update(XDG_CONFIG_HOME=str(lab/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
rows=[]
try:
    for flow in ('expanded','execute'):
        dest=out/flow;dest.mkdir()
        (dest/'prior.wcprof').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
        marker=f'\n// wcprof new user-code edit {flow} {time.time_ns()}\n'.encode()
        (app/'main.go').write_bytes(original+marker)
        command=[str(x.CLI),'--engine','container://'+item['name'],'--profile']+x.FLOWS[flow]
        done=threading.Event();observed={}
        with (dest/'stdout.txt').open('wb') as stdout,(dest/'stderr.txt').open('wb') as stderr:
            begin=time.monotonic();wall=time.time_ns()
            process=subprocess.Popen(command,cwd=app,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            def waiter():
                observed['status']=process.wait();observed['time']=time.monotonic();observed['wall']=time.time_ns();done.set()
            worker=threading.Thread(target=waiter,daemon=True);worker.start()
            try:
                if not done.wait(180):raise TimeoutError('profiled CLI deadline')
            finally:
                if not done.is_set():
                    process.send_signal(signal.SIGINT)
                    if not done.wait(10):os.killpg(process.pid,signal.SIGKILL)
                worker.join(timeout=15);assert not worker.is_alive()
        assert observed['status']==0,'profiled command failed; inspect private output'
        stdout=(dest/'stdout.txt').read_bytes();stderr=(dest/'stderr.txt').read_bytes()
        if flow=='expanded':assert stdout==x.WANT
        else:
            text=re.sub(rb'\x1b\[[0-9;]*m',b'',stdout+stderr)
            assert b'dag://go/modules/tests/run?go-module=.&go-test=TestFormatResponse' in text and re.search(rb'\b1 passed\b',text)
        time.sleep(.3)
        (dest/'run.wcprof').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
        row={'flow':flow,'seconds':observed['time']-begin,'started_unix_ns':wall,'exited_unix_ns':observed['wall'],'exit_code':observed['status'],'source_sha256':x.sha(app/'main.go'),'stdout_sha256':x.sha(dest/'stdout.txt'),'engine_sha256':item['sha256'],'correct':True,'profile':True}
        rows.append(row);x.write(out/'results.json',rows);print(json.dumps(row),flush=True)
finally:
    (app/'main.go').write_bytes(original)
    assert x.sha(app/'main.go')==manifest['source_hashes']['main.go']
    x.write(out/'restoration.json',{'source_restored':True})
