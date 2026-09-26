from pathlib import Path
import subprocess,os,time,json,hashlib,statistics,urllib.request
B=Path('/tmp/collections-perf/sdk-edit-audit/ts-static');dest=B/'measurements';dest.mkdir(exist_ok=True)
ws=B/'greetings';cli='/tmp/collections-perf/rebase-main/dagger'; want=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
variants={'control':('dagger-engine.collections-disk-abba-1',6171),'static':('dagger-engine.collections-disk-abba-2',6172)}
env=dict(os.environ)
for k in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN']:env.pop(k,None)
def psi():return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=',1)[1])
def normalized(data):return sorted(tuple(p.strip() for p in l.split('#',1)) for l in data.decode().splitlines() if l.strip())
rows=[]
def run(label,key,expected=want,iteration=0,profile=False):
 name,port=variants[label];before=psi();start=time.monotonic();args=[cli,'--engine','container://'+name]
 if profile:args+=['--profile']
 p=subprocess.run(args+['check','-l','--all'],cwd=ws,env=env,capture_output=True);elapsed=time.monotonic()-start;after=psi()
 (dest/f'{key}-{label}.out').write_bytes(p.stdout);(dest/f'{key}-{label}.err').write_bytes(p.stderr)
 correct=p.returncode==0 and normalized(p.stdout)==normalized(expected)
 row={'variant':label,'case':key,'iteration':iteration,'seconds':elapsed,'host_io_full_seconds':(after-before)/1e6,'correct':correct,'status':p.returncode,'rows':len(p.stdout.splitlines()),'stdout_sha256':hashlib.sha256(p.stdout).hexdigest()}
 rows.append(row);(dest/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 assert correct,row
 if profile:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump',timeout=60) as r:(dest/(label+'.wcprof')).write_bytes(r.read())
 return row
for i in range(-2,8):
 labels=list(variants)
 if i%2:labels.reverse()
 for label in labels:run(label,'warm-'+str(i),iteration=i)
summary={'warm':{label:{'median':statistics.median(v:=[r['seconds'] for r in rows if r['case'].startswith('warm-') and r['iteration']>=0 and r['variant']==label]),'min':min(v),'max':max(v),'n':len(v)} for label in variants}}
(dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
for label in variants:run(label,'profile',profile=True)
edit=ws/'main_test.go';original=edit.read_bytes()
try:
 for cycle in range(3):
  rename=f'TestFormatResponseStaticProbe{cycle}'.encode();added=f'TestStaticMetadataProbe{cycle}'.encode()
  addline=b'--go-module=. --go-test='+added+b' dag+check://go/modules/tests/run # Run this test.\n'
  edits=[('comment',original+f'\n// discovery performance edit {cycle}\n'.encode(),want),('rename',original.replace(b'TestFormatResponse(',rename+b'('),want.replace(b'TestFormatResponse ',rename+b' ')),('add',original+b'\nfunc '+added+b'(t *testing.T) {}\n',want+addline),('restore',original,want)]
  for case,contents,expected in edits:
   edit.write_bytes(contents)
   labels=list(variants)
   if (cycle+len(case))%2:labels.reverse()
   for label in labels:run(label,f'edit-{case}-{cycle}',expected,iteration=cycle)
finally:edit.write_bytes(original)
for case in ['comment','rename','add','restore']:
 summary[case]={label:{'median':statistics.median(v:=[r['seconds'] for r in rows if r['case'].startswith('edit-'+case+'-') and r['variant']==label]),'min':min(v),'max':max(v),'n':len(v)} for label in variants}
(dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
