from pathlib import Path
import json,os,subprocess,time,urllib.request
root=Path(__file__).parent
base=root.parent
module=Path('/tmp/dagger-go-parallel-validation')
def get(route,data=None):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as r:return json.load(r)
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
testfile=module/'.dagger/modules/go-dev/main.dang'
original=testfile.read_bytes()
extra=(Path('/tmp/dagger-go-native-module-lookup/.dagger/modules/go-dev/main.dang').read_text().split('  packageOwnershipCheck: Void @check {',1)[1].split('  testsCollectionCheck(',1)[0])
nonce=str(time.time_ns())
additional=('  packageOwnershipCheck: Void @check {'+extra).replace('func TestSub(t *testing.T) {}', 'func TestSub(t *testing.T) {}\\n// unique ownership input '+nonce)
fixture=next((module/'testdata/go-module-with-testdata').glob('*_test.go'))
fixture_original=fixture.read_bytes()
rows=[]
saved=get('reusable-declarations')['enabled']
flush_saved=get('telemetry-flush-coalescing')['enabled']
callback_saved=get('callback-caller-reuse')['enabled']
interfaces_saved=get('interface-field-snapshots')['enabled']
try:
 fixture.write_bytes(fixture_original+('\n// unique declaration reuse verification '+nonce+'\n').encode())
 testfile.write_text(original.decode().replace('  testsCollectionCheck(',additional+'  testsCollectionCheck(',1))
 assert get('reusable-declarations?enabled=true',b'')['enabled']
 assert get('interface-field-snapshots?enabled=true',b'')['enabled']
 assert not get('telemetry-flush-coalescing?enabled=false',b'')['enabled']
 assert not get('callback-caller-reuse?enabled=false',b'')['enabled']
 for check in ['go-dev:package-ownership-check','go-dev:tests-collection-check']:
  tick=time.monotonic();before=get('reusable-declarations')
  with (root/(check.replace(':','-')+'.log')).open('w') as out:
   r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
  row=dict(check=check,exit_code=r.returncode,seconds=time.monotonic()-tick,declarations_before=before,declarations_after=get('reusable-declarations'))
  rows.append(row);(root/'integration-correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
  assert r.returncode==0,check
finally:
 fixture.write_bytes(fixture_original)
 testfile.write_bytes(original)
 assert get('reusable-declarations?enabled='+str(saved).lower(),b'')['enabled']==saved
 assert get('telemetry-flush-coalescing?enabled='+str(flush_saved).lower(),b'')['enabled']==flush_saved
 assert get('callback-caller-reuse?enabled='+str(callback_saved).lower(),b'')['enabled']==callback_saved
 assert get('interface-field-snapshots?enabled='+str(interfaces_saved).lower(),b'')['enabled']==interfaces_saved
