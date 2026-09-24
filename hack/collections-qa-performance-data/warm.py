from pathlib import Path
import subprocess,sys,json,statistics,hashlib
base=Path('/tmp/collections-perf/greetings')
runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
expected=(base/'original-first-use/run-0.out').read_bytes()
assert len(expected.splitlines())==14
variants={
 'original':('/tmp/collections-perf/untouched-pr/dagger','container://dagger-engine.collections-untouched','/tmp/greetings-api-collections-perf'),
 'engine-only':('/tmp/collections-perf/dagger-pinned-discovery','container://dagger-engine.collections-profile-stack','/tmp/greetings-api-collections-perf'),
 'full-stack':('/tmp/collections-perf/dagger-pinned-discovery','container://dagger-engine.collections-profile-stack','/tmp/greetings-api-optimized-perf'),
}
def run(variant,label,profile=False):
    cli,engine,cwd=variants[variant];dest=base/label
    args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest)]
    if profile: args+=['--wcprof-url','http://127.0.0.1:'+('6080' if variant=='original' else '6066')]
    args+=['--',cli,'--engine',engine,'check','-l','--all']
    p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (dest/'driver.log').write_text(p.stdout);p.check_returncode()
    output=(dest/'run-0.out').read_bytes()
    assert output==expected, f'{variant}: listing differs; inspect {dest}'
    result=json.loads((dest/'results.json').read_text())
    row={'variant':variant,'label':label,'seconds':result['median_seconds'],'sha256':hashlib.sha256(output).hexdigest(),'rows':len(output.splitlines())}
    print(json.dumps(row),flush=True)
    if profile:
        with (dest/'analysis.txt').open('w') as f: subprocess.run(['/tmp/wcprof-analyze','-top','70',str(dest/'runs.wcprof')],stdout=f,check=True)
    return row
for variant in ['engine-only','full-stack']: run(variant,variant+'-first-use')
rows=[]
for i in range(5):
    order=list(variants);order=order[i%3:]+order[:i%3]
    for variant in order:
        rows.append(run(variant,f'warm/{variant}-{i}'))
        summary={v:{'samples_seconds':[r['seconds'] for r in rows if r['variant']==v],'median_seconds':statistics.median(r['seconds'] for r in rows if r['variant']==v)} for v in variants if any(r['variant']==v for r in rows)}
        (base/'warm-summary.json').write_text(json.dumps({'variants':summary,'rows':rows,'complete_output_matches':True},indent=2)+'\n')
for variant in variants: run(variant,'profile-'+variant,True)
print('Warm comparison and profiles complete.',flush=True)
