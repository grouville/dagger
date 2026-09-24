from pathlib import Path
import subprocess,sys,json,shlex,uuid,shutil,os
os.environ.pop("SSH_AUTH_SOCK",None)
base=Path('/tmp/collections-perf/normal-baseline/invalidation')
base.mkdir(exist_ok=True)
runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
variants={
 'original':('/tmp/collections-perf/untouched-pr/dagger','container://dagger-engine.collections-normal-original',Path('/tmp/collections-perf/published-baseline/greetings-pristine')),
 'committed':('/tmp/collections-perf/committed/dagger','container://dagger-engine.collections-normal-committed',Path('/tmp/collections-perf/normal-baseline/greetings-committed')),
 'candidate':('/tmp/collections-perf/committed/dagger','container://dagger-engine.collections-normal-syntax',Path('/tmp/collections-perf/normal-baseline/greetings-split')),
}
if not variants['committed'][2].exists():
 shutil.copytree(variants['original'][2], variants['committed'][2])

def keys(data):
    out=[]
    for line in data.decode().splitlines():
        words=shlex.split(line.partition('#')[0])
        if not words: continue
        uri=[s for s in words if s.startswith('dag+check://')]
        assert len(uri)==1,line
        out.append((uri[0],tuple(sorted(s for s in words if s.startswith('--')))))
    assert len(out)==len(set(out)),'duplicate check'
    return set(out)
baseline=keys(Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes());assert len(baseline)==14
originals={v:{p:(ws/p).read_bytes() for p in ['main.go','main_test.go','go.mod']} for v,(_,_,ws) in variants.items()}
nonce=uuid.uuid4().hex; marker=f'\n// discovery benchmark {nonce}\n'.encode()
added='perf-added-module'
for _,_,ws in variants.values(): assert not (ws/added).exists()
phases=['unchanged','comment-edit','rename-test','add-test','add-module','restore']
rows=[]
try:
 for i,phase in enumerate(phases):
    expected=set(baseline)
    for variant,(_,_,ws) in variants.items():
        for path,data in originals[variant].items(): (ws/path).write_bytes(data)
        if (ws/added).exists(): shutil.rmtree(ws/added)
        if phase=='comment-edit': (ws/'main.go').write_bytes(originals[variant]['main.go']+marker)
        elif phase=='rename-test': (ws/'main_test.go').write_bytes(originals[variant]['main_test.go'].replace(b'func TestSelectGreeting(',b'func TestPerfRenamed(')+marker)
        elif phase=='add-test': (ws/'main_test.go').write_bytes(originals[variant]['main_test.go']+b'\nfunc TestPerfAdded(t *testing.T) {}\n'+marker)
        elif phase=='add-module':
            (ws/added).mkdir();(ws/added/'go.mod').write_bytes(b'module example.com/discovery-perf\n\ngo 1.26.1\n'+marker)
            (ws/added/'new_test.go').write_text('package perf\nimport "testing"\nfunc TestPerfModule(t *testing.T) {}\n')
    if phase=='rename-test':
        expected={(uri,tuple(s.replace('--go-test=TestSelectGreeting','--go-test=TestPerfRenamed') for s in args)) for uri,args in baseline}
    elif phase=='add-test': expected.add(('dag+check://go/modules/tests/run',('--go-module=.','--go-test=TestPerfAdded')))
    elif phase=='add-module':
        expected.add(('dag+check://go/modules/generate/stale',('--go-module='+added,)))
        expected.add(('dag+check://go/modules/tests/run',('--go-module='+added,'--go-test=TestPerfModule')))
    observed={}
    for variant in (list(variants) if i%2==0 else list(reversed(variants))):
        cli,engine,ws=variants[variant];dest=base/'edits'/phase/variant
        p=subprocess.run([sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--',cli,'--engine',engine,'check','-l','--all'],cwd=ws,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (dest/'driver.log').write_text(p.stdout);p.check_returncode()
        data=(dest/'run-0.out').read_bytes();actual=keys(data)
        assert actual==expected, f'{phase}/{variant}: missing={expected-actual}; extra={actual-expected}'
        result=json.loads((dest/'results.json').read_text());observed[variant]=data
        row={'phase':phase,'variant':variant,'seconds':result['median_seconds'],'rows':len(actual),'correct':True,'iteration':nonce}
        rows.append(row);print(json.dumps(row),flush=True)
    assert len(set(observed.values()))==1,phase+' order/description/format differs'
    (base/'edit-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
finally:
 for variant,(_,_,ws) in variants.items():
    for path,data in originals[variant].items(): (ws/path).write_bytes(data)
    if (ws/added).exists(): shutil.rmtree(ws/added)
