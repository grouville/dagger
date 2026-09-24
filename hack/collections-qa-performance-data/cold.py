from pathlib import Path
import subprocess, time, json, socket, shutil, hashlib
base=Path('/tmp/collections-perf/greetings')
runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
expected=(base/'original-first-use/run-0.out').read_bytes()
records=[]
for variant,module in [('original','/tmp/dagger-go-collections'),('full-stack','/tmp/dagger-go-discovery')]:
    ws=base/('cold-workspace-'+variant)
    if not ws.exists():
        subprocess.run(['git','clone','--quiet','--shared','/tmp/greetings-api-collections-perf',str(ws)],check=True)
        subprocess.run(['git','-C',str(ws),'remote','set-url','origin','https://github.com/kpenfound/greetings-api.git'],check=True)
        shutil.copy2('/tmp/greetings-api-collections-perf/dagger.lock',ws/'dagger.lock')
        config=ws/'dagger.toml'
        config.write_text(config.read_text().replace('source = "github.com/dagger/go@collections"','source = "'+module+'"'))
for round_index,order in enumerate([['original','full-stack'],['full-stack','original']]):
    for variant in order:
        name=f'dagger-engine.greetings-cold-{variant}-{round_index}'
        port=6081+len(records)
        dest=base/f'cold-{variant}-{round_index}'
        for kind in ['container','volume']:
            assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0, name+' exists'
        assert not dest.exists(), str(dest)+' exists'
        cli='/tmp/collections-perf/untouched-pr/dagger' if variant=='original' else '/tmp/collections-perf/dagger-pinned-discovery'
        engine='/tmp/collections-perf/untouched-pr/engine' if variant=='original' else '/tmp/collections-perf/engine-prepared-authority'
        subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','localhost/dagger-engine.collections-perf:latest','--extra-debug','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['docker','cp',engine,name+':/usr/local/bin/dagger-engine'],check=True)
        subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+30
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=1): break
                except OSError:
                    if time.monotonic()>deadline: raise
                    time.sleep(.1)
            print('Measuring '+name,flush=True)
            args=['python3',runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--',cli,'--engine','container://'+name,'check','-l','--all']
            p=subprocess.run(args,cwd=base/('cold-workspace-'+variant),capture_output=True,text=True)
            (dest/'driver.log').write_text(p.stdout+p.stderr)
            data=json.loads((dest/'results.json').read_text())
            output=(dest/'run-0.out').read_bytes()
            row={'variant':variant,'round':round_index,'seconds':data['median_seconds'],'exit_code':p.returncode,'correct':output==expected,'rows':len(output.splitlines()),'sha256':hashlib.sha256(output).hexdigest(),'engine':name}
            records.append(row);(base/'cold-summary.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(row),flush=True)
            p.check_returncode();assert output==expected, str(dest)
        finally:
            subprocess.run(['docker','stop',name],check=True,stdout=subprocess.DEVNULL)
