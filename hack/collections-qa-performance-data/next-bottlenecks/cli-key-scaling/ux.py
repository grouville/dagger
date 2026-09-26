"""Fresh CLI processes for real navigation/list/check flows; caller owns engine slot."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, statistics, subprocess, time, urllib.request, urllib.error

lab=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--run',action='store_true')
parser.add_argument('--pairs',type=int,default=4)
parser.add_argument('--local-only',action='store_true')
parser.add_argument('--trial',default='ux')
parser.add_argument('--baseline-cli',default=str(lab/'dagger-baseline'))
parser.add_argument('--candidate-cli',default=str(lab/'dagger-candidate'))
args=parser.parse_args()
flows={
    'overview':['list'],
    'static-checks':['check','-l'],
    'expanded-checks':['check','-l','--all'],
    'filtered-checks':['check','-l','--all','go/modules/tests/run','--go-module=.','--go-test=TestFormatResponse'],
    'type-checks':['list','checks','go/modules/tests/run','-f','link'],
    'modules':['list','go-modules','-f','link'],
    'tests':['list','go-tests','-f','link'],
    'check-help':['check','go/modules/tests/run','--help'],
    'generators':['generate','-l','--all'],
    'services':['up','-l','--all'],
    'workspace-files':['ws','ls'],
    'execute-single':['check','--generated=false','go/modules/tests/run','--go-module=.','--go-test=TestFormatResponse'],
}
if not args.run:
    print(json.dumps({'status':'prepared, not run','flows':flows},indent=2));raise SystemExit()
assert '/' not in args.trial and args.trial not in ('','.','..')
out=lab/args.trial;out.mkdir(exist_ok=False)
(out/'driver.py.txt').write_text(Path(__file__).read_text())
source=Path('/tmp/collections-perf/sdk-edit-audit/ts-static/greetings')
app=out/'greetings';shutil.copytree(source,app,symlinks=True)
engine='dagger-engine.collections-disk-abba-2'
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
env=dict(os.environ)
for k in ('SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','DAGGER_CLOUD_URL','_DAGGER_CLI_TIMING_DIAG','DAGGER_CLOUD_BATCH_DIAGNOSTICS'):
    env.pop(k,None)
if args.local_only:
    config=out/'empty-config';config.mkdir(mode=0o700)
    for key in list(env):
        if key.startswith(('OTEL_','DAGGER_SESSION_','DAGGER_CLOUD_')) or key in ('DAGGER_CONFIG','TRACEPARENT','TRACESTATE','BAGGAGE','_EXPERIMENTAL_DAGGER_CACHE_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG','_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG','_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT'):env.pop(key,None)
    env.update(XDG_CONFIG_HOME=str(config),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1')
telemetry_mode='local-only empty credentials; no Cloud or OTLP exporters or analytics' if args.local_only else 'normal direct Cloud'
clis={'baseline':args.baseline_cli,'candidate':args.candidate_cli}
originals={name:(app/name).read_bytes() for name in ('main.go','main_test.go','dagger.toml')}
rows=[];canonical={}
def sha(data):return hashlib.sha256(data).hexdigest()
def psi():return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=',1)[1])
def dump(path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:6172/debug/wcprof/dump?flush=true',timeout=20) as f:path.write_bytes(f.read())
    except urllib.error.HTTPError as e:
        if e.code!=503:raise
def run(variant,flow,label,want=None,profile=False):
    dest=out/label;dest.mkdir(parents=True,exist_ok=False)
    if profile:dump(dest/'prior.wcprof')
    cmd=[clis[variant],'--engine','container://'+engine]+(['--profile'] if profile else [])+flows[flow]
    before=psi();wall_start=time.time_ns();start=time.monotonic();p=subprocess.run(cmd,cwd=app,env=env,capture_output=True,timeout=600);elapsed=time.monotonic()-start;wall_exit=time.time_ns();after=psi()
    (dest/'stdout.txt').write_bytes(p.stdout);(dest/'stderr.txt').write_bytes(p.stderr)
    if p.returncode:raise RuntimeError((label,p.returncode,p.stderr[-2000:].decode(errors='replace')))
    if flow=='execute-single':
        text=re.sub(r'\x1b\[[0-9;]*m','',(p.stdout+p.stderr).decode(errors='replace'))
        assert re.search(r'== CHECKS ==.*\b1 passed\b',text),text[-2000:]
    else:
        if want is not None:assert p.stdout==want,(label,'explicit expected output mismatch')
        elif label.startswith(('warmup/','warm/','profile/')):
            if flow not in canonical:canonical[flow]=p.stdout
            assert p.stdout==canonical[flow],(label,'control output mismatch')
        if flow=='expanded-checks' and '/edit-' not in label:assert p.stdout==expected,label
        if flow=='filtered-checks':assert len(p.stdout.splitlines())==1 and b'TestFormatResponse' in p.stdout,label
        if flow=='modules':assert len(p.stdout.splitlines())==3,label
        if flow in ('tests','type-checks'):assert len(p.stdout.splitlines())==6,label
        if flow=='check-help':assert b'--go-test' in p.stdout and b'USAGE' in p.stdout,label
    row={'variant':variant,'flow':flow,'label':label,'seconds':elapsed,'exit_code':p.returncode,'profile':profile,'stdout_sha256':sha(p.stdout),'correct':True,'io_full_stall_seconds':(after-before)/1e6,'command':cmd,'telemetry_mode':telemetry_mode}
    if profile:row.update({'started_unix_ns':wall_start,'exited_unix_ns':wall_exit})
    rows.append(row);(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    if profile:dump(dest/'run.wcprof')
manifest={'boundary':'fresh process through exit; retained static-TS engine, no cold claim','engine':engine,'telemetry_mode':telemetry_mode,'selected_cli_paths':clis,'selected_cli_sha256':{k:sha(Path(v).read_bytes()) for k,v in clis.items()},'driver_sha256':sha(Path(__file__).read_bytes()),'source':str(source),'source_hashes':{n:sha(d) for n,d in originals.items()},'cli_build':json.loads((lab/'build-provenance.json').read_text()),'flows':flows}
(out/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
try:
    for flow in flows:
        for v in ('baseline','candidate'):run(v,flow,'warmup/'+flow+'-'+v)
    for i in range(args.pairs):
        for flow in flows:
            for v in (('baseline','candidate') if i%2==0 else ('candidate','baseline')):
                run(v,flow,f'warm/{i}-{flow}-{v}')
    # Correctness probes, NOT paired edit speed claims: the first run can prewarm shared content.
    # Identical real application edits for each CLI; normal Dagger invalidation.
    for edit in ('comment','rename','add','restore'):
        main=originals['main.go'];tests=originals['main_test.go'];want=expected
        if edit=='comment':main+=b'\n// CLI performance audit: ordinary application edit.\n'
        if edit=='rename':
            tests=tests.replace(b'func TestFormatResponse(',b'func TestFormatResponze(')
            want=expected.replace(b'TestFormatResponse',b'TestFormatResponze')
        if edit=='add':
            # Addition is checked by keys rather than layout, which changes column padding.
            tests+=b'\nfunc TestCLIListingFreshness(t *testing.T) {}\n'
            want=None
        (app/'main.go').write_bytes(main);(app/'main_test.go').write_bytes(tests)
        for v in ('baseline','candidate'):
            run(v,'expanded-checks',f'edits/edit-{edit}-{v}',want=want)
            if edit=='add':
                data=(out/f'edits/edit-{edit}-{v}/stdout.txt').read_bytes()
                assert len(data.splitlines())==15 and data.count(b'--go-test=TestCLIListingFreshness ')==1
        assert (out/f'edits/edit-{edit}-baseline/stdout.txt').read_bytes()==(out/f'edits/edit-{edit}-candidate/stdout.txt').read_bytes()
    for flow in ('overview','static-checks','expanded-checks','modules','tests','execute-single','generators','services','workspace-files'):
        run('candidate',flow,'profile/'+flow,profile=True)
finally:
    for name,data in originals.items():(app/name).write_bytes(data)
    restored={name:(app/name).read_bytes()==data and (source/name).read_bytes()==data for name,data in originals.items()}
    (out/'restoration.json').write_text(json.dumps(restored,indent=2)+'\n')
    assert all(restored.values())
summary=[]
for flow in flows:
    row={'flow':flow}
    for v in ('baseline','candidate'):
        samples=[r['seconds'] for r in rows if r['flow']==flow and r['variant']==v and r['label'].startswith('warm/')]
        row[v]={'median_seconds':statistics.median(samples),'samples':samples}
    summary.append(row)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
