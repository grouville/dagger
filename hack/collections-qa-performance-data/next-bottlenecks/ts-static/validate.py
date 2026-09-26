from pathlib import Path
import argparse,subprocess,os,json,time
ap=argparse.ArgumentParser()
ap.add_argument('--cli',required=True)
ap.add_argument('--engine',required=True)
ap.add_argument('--control-engine')
a=ap.parse_args()
out=Path('/tmp/collections-perf/sdk-edit-audit/ts-static')
app=out/'greetings'; mod=app/'.dagger/modules/frontend'
logs=out/'validation'; logs.mkdir(exist_ok=True)
env=dict(os.environ)
for key in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN']:
 env.pop(key,None)
rows=[]
def run(label,args,engine=None,want_stale=False):
 start=time.monotonic()
 p=subprocess.run([a.cli,'--engine',engine or a.engine]+args,cwd=app,env=env,capture_output=True)
 elapsed=time.monotonic()-start
 (logs/(label+'.out')).write_bytes(p.stdout);(logs/(label+'.err')).write_bytes(p.stderr)
 ok=(p.returncode!=0 and b'static TS metadata stale' in p.stderr) if want_stale else p.returncode==0
 row={'label':label,'seconds':elapsed,'exit':p.returncode,'correct':ok}
 rows.append(row);print(json.dumps(row),flush=True)
 (logs/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 if not ok: raise RuntimeError('failed '+label+'; inspect logs')
 return p.stdout
listing=run('listing',['check','-l','--all'])
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
assert listing==expected,'listing differs'
for name in ['source','build']:
 args=['-m','.dagger/modules/frontend','call',name,'entries']
 candidate=run('call-'+name,args)
 if a.control_engine:
  control=run('control-call-'+name,args,engine=a.control_engine)
  assert candidate==control, 'runtime output differs: '+name
# The fixture guard is conservative: changing source body/API/config/bindings
# rejects the static path, and never silently keeps stale registration.
mutations=[
 ('api-edit', 'src/index.ts', lambda b:b.replace(b'  @func()\n  build()',b'  @func()\n  ping(): string { return "ok"; }\n\n  @func()\n  build()')),
 ('config-edit','tsconfig.json',lambda b:b+b'\n'),
 ('binding-edit','sdk/client.gen.ts',lambda b:b+b'\n// freshness probe\n'),
]
for label,rel,change in mutations:
 p=mod/rel;before=p.read_bytes()
 try:
  after=change(before);assert after!=before,label
  p.write_bytes(after)
  run(label,['-m','.dagger/modules/frontend','call','build','entries'],want_stale=True)
 finally:p.write_bytes(before)
p=mod/'src/static_metadata_probe.ts'
assert not p.exists()
try:
 p.write_text('export const probe = true\n')
 run('added-input',['-m','.dagger/modules/frontend','call','build','entries'],want_stale=True)
finally:p.unlink()
assert run('restored',['check','-l','--all'])==expected
print('All metadata guards and original TS runtime calls passed',flush=True)
