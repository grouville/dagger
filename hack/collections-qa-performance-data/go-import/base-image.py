from pathlib import Path
import os,sys,subprocess,json,urllib.request
os.environ.pop('SSH_AUTH_SOCK',None)
base=Path('/tmp/collections-perf/go-import');rows=[];expected=None
for variant,port in [('control',6122),('candidate',6123)]:
    name=f'dagger-engine.collections-go-import-{variant}-0';dest=base/'base-image'/variant;dest.mkdir(parents=True)
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump') as r:(dest/'before.wcprof').write_bytes(r.read())
    cmd=[sys.executable,'/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--timeout','300','--output',str(dest),'--wcprof-url',f'http://127.0.0.1:{port}','--cold-profile','--','/tmp/collections-perf/committed/dagger','--engine','container://'+name,'api','query','-M','--doc',str(base/'base-image.graphql')]
    p=subprocess.run(cmd,cwd='/tmp',capture_output=True,text=True);(dest/'driver.log').write_text(p.stdout+p.stderr)
    p.check_returncode()
    data=(dest/'run-0.out').read_bytes();v=json.loads(data)
    assert v['container']['from']['file']['contents'].startswith('go1.26')
    if expected is None:expected=data
    assert data==expected
    with (dest/'runs.wcprof').open() as f:
        h=json.loads(next(f));s=h['strings'];events=[json.loads(x) for x in f]
    layers=[{'class':s[x.get('c',0)],'digest':s[x.get('i',0)],'seconds':(x['d']-x['s'])/1e9} for x in events if s[x.get('c',0)] in ['image.importLayer','image.applyLayer']]
    (dest/'layers.json').write_text(json.dumps(layers,indent=2)+'\n')
    row={'variant':variant,'seconds':json.loads((dest/'results.json').read_text())['median_seconds'],'applied_layers':sum(x['class']=='image.applyLayer' for x in layers),'correct':True};rows.append(row)
    (base/'base-image/summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
