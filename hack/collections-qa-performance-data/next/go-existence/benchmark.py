from pathlib import Path
import subprocess,os,sys,json,statistics
base=Path('/tmp/collections-perf/go-existence');os.environ.pop('SSH_AUTH_SOCK',None)
cli='/tmp/collections-perf/committed/dagger';engine='container://dagger-engine.collections-kyle-syntax';runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
modules={'baseline':'/tmp/dagger-go-kyle-latest','existence':'/tmp/dagger-go-kyle-existence'}
rows=[]
for count in [64,256,512]:
 ws=base/f'files-{count}';ws.mkdir(exist_ok=False);subprocess.run(['git','init','-q',str(ws)],check=True)
 (ws/'go.mod').write_text('module example.com/file-count\n\ngo 1.26.1\n')
 for i in range(count):(ws/f'file{i:05}.go').write_text('package sample\n')
 expected=None
 for round_no in range(-1,3):
  order=list(modules) if round_no%2==0 else list(reversed(modules))
  for name in order:
   (ws/'dagger.toml').write_text('[modules.go]\nsource = "'+modules[name]+'"\n')
   dest=base/f'n{count}'/f'{name}-{round_no}'
   args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','180','--output',str(dest),'--',cli,'--engine',engine,'check','-l','--all']
   p=subprocess.run(args,cwd=ws,capture_output=True,text=True);(dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
   output=(dest/'run-0.out').read_bytes()
   if expected is None:expected=output
   assert output==expected,('different output',count,name)
   result=json.loads((dest/'results.json').read_text());row={'files':count,'variant':name,'round':round_no,'seconds':result['median_seconds'],'rows':len(output.splitlines()),'correct':True};rows.append(row)
   print(json.dumps(row),flush=True);(base/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
summary={str(n):{v:statistics.median(r['seconds'] for r in rows if r['files']==n and r['variant']==v and r['round']>=0) for v in modules} for n in [64,256,512]}
(base/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
