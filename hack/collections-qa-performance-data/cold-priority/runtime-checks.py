from pathlib import Path
import subprocess,os,json,uuid
base=Path('/tmp/collections-perf/ts-runtime-manifest/runtime-checks');base.mkdir(exist_ok=True)
os.environ.pop('SSH_AUTH_SOCK',None)
cli='/tmp/collections-perf/committed/dagger';engine='container://dagger-engine.collections-ts-runtime-manifest'
rows=[];nonce=uuid.uuid4().hex
for variant,ws in [('control',Path('/tmp/collections-perf/published-baseline/greetings-pristine')),('split',Path('/tmp/collections-perf/normal-baseline/greetings-split'))]:
 source=ws/'.dagger/modules/frontend/src/index.ts';original=source.read_bytes()
 def call(label,path,expected=None,error=False):
  command=[cli,'--engine',engine,'api','call','-m','.dagger/modules/frontend','build','file','--path',path,'contents']
  result=subprocess.run(command,cwd=ws,capture_output=True,timeout=180)
  dest=base/(variant+'-'+label);dest.with_suffix('.out').write_bytes(result.stdout);dest.with_suffix('.err').write_bytes(result.stderr)
  assert (result.returncode!=0)==error,(variant,label,result.returncode,result.stderr[-2000:])
  if expected is not None: assert result.stdout.rstrip(b'\n')==expected.rstrip(b'\n'),(variant,label,'output differs')
  if error: assert b'SDK_SPLIT_RUNTIME_ERROR' in result.stderr,(variant,label,'missing error')
  rows.append({'variant':variant,'case':label,'status':result.returncode,'correct':True});(base/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(rows[-1],flush=True)
 try:
  call('original','index.html',(ws/'website/index.html').read_bytes())
  assert original.count(b'return this.source;')==1
  source.write_bytes(original.replace(b'return this.source;',('return this.source.withNewFile("perf-marker", "'+nonce+'");').encode()))
  call('body-edit','perf-marker',nonce.encode())
  source.write_bytes(original.replace(b'return this.source;',b'throw new Error("SDK_SPLIT_RUNTIME_ERROR");'))
  call('error','index.html',error=True)
 finally: source.write_bytes(original)
 call('restore','index.html',(ws/'website/index.html').read_bytes())
print('Both runtimes execute the changed function and propagate errors; sources restored.',flush=True)
