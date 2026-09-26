"""Complete correctness/profiles without repeating or replacing measured pairs.

The first missing-base negative failed at C compilation, so it is retained as
an unaccepted control. Remove just the URL in the configured base instead.
"""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,signal,statistics,subprocess,threading,time
import experiment as x
lab=Path(__file__).resolve().parent;out=lab/'withfile-v1'
state=json.loads((out/'prepared.json').read_text())
rows=json.loads((out/'results.json').read_text());assert len(rows)==58
assert not (out/'summary.json').exists()
app=lab/'greetings';assert x.fixture_hashes(app)==state['input_sha256']
for v in ('base','candidate'):x.start(state[v])
original={n:(app/n).read_bytes() for n in (*state['source_hashes'],'e2e_test.go','.dagger/modules/backend/main.go')}
nonce=hex(time.time_ns())[2:]
env={k:os.environ[k] for k in ('PATH','HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
env.update(XDG_CONFIG_HOME=str(lab/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
flows={k:x.FLOWS[k] for k in ('expanded','filtered','execute')}
flows['e2e']=['check','--generated=false','go/modules/tests/run','--go-module=.','--go-test=TestE2ERandomGreeting']
frozen=out/'driver.py.txt'
tree=ast.parse(frozen.read_text());funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run'];assert len(funcs)==1
exec(compile(ast.Module(body=funcs,type_ignores=[]),str(frozen),'exec'))
negative=out/'correctness-missing-base-0-e2e-candidate'
x.write(out/'unaccepted-negative-control.json',{'reason':'removing base changed compiler environment; command failed at missing gcc before the strict HTTP test','candidate_engine':state['candidate']['sha256'],'expected_outcome_observed':False,'stderr_sha256':x.sha(negative/'stderr.txt'),'stdout_sha256':x.sha(negative/'stdout.txt'),'excluded_from_validated_rows':True,'replacement':'preserve configured base and clear only GREETINGS_API_URL'})
x.write(out/'followup-provenance.json',{'nonce':nonce,'driver_sha256':x.sha(__file__),'run_function_source_sha256':x.sha(frozen),'commands':5,'preserved_validated_rows':58,'negative_control':'same configured base, empty GREETINGS_API_URL; original strict t.Skip changed to t.Fatal','profiles':'new source bytes per flow, same bytes per variant, no prelisting before execute'})
(out/'followup-driver.py.txt').write_bytes(Path(__file__).read_bytes())
try:
    assert original['e2e_test.go'].count(b't.Skip(')==1
    (app/'e2e_test.go').write_bytes(original['e2e_test.go'].replace(b't.Skip(',b't.Fatal('))
    backend='.dagger/modules/backend/main.go';address=b'WithEnvVariable("GREETINGS_API_URL", "http://api:8080")'
    assert original[backend].count(address)==1
    (app/backend).write_bytes(original[backend].replace(address,b'WithEnvVariable("GREETINGS_API_URL", "")'))
    run('candidate','e2e','correctness-missing-url',0,fail=True)
    (app/backend).write_bytes(original[backend]);(app/'e2e_test.go').write_bytes(original['e2e_test.go'])
    for flow in ('expanded','execute'):
        (app/'main.go').write_bytes(original['main.go']+f'\n// withfile followup {nonce} profile {flow}\n'.encode())
        for v in ('base','candidate'):run(v,flow,'profile',0,profile=True)
finally:
    for n,b in original.items():(app/n).write_bytes(b)
    assert x.fixture_hashes(app)==state['input_sha256']
    x.write(out/'restoration.json',{'source_restored':True,'full_fixture_restored':True,'e2e_source_sha256':x.sha(app/'e2e_test.go'),'backend_source_sha256':x.sha(app/backend)})
summary=[]
for phase,flow in sorted({(r['phase'],r['flow']) for r in rows if not r['profile']}):
    item={'phase':phase,'flow':flow}
    for v in ('base','candidate'):
        vals=[r['seconds'] for r in rows if r['phase']==phase and r['flow']==flow and r['variant']==v]
        item[v]={'n':len(vals),'samples':vals,'median_seconds':statistics.median(vals) if vals else None}
    summary.append(item)
x.write(out/'summary.json',summary)
