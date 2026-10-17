from pathlib import Path
import hashlib,json,os,signal,subprocess,time
protocol=Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
family=Path(__file__).parent; cli=family/'dagger-counts';env.update(_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15',_EXPERIMENTAL_DAGGER_NATIVE_WALK_COUNTS='1')
source=Path('/tmp/dagger-go-real-repository-main');module=Path('/tmp/dagger-go-module-test-name-index');edit=source/'dagql/types.go';original=edit.read_bytes()
saved={n:(source/n).read_bytes() if (source/n).exists() else None for n in ['dagger.toml','dagger.lock']}
routes=['batch-metadata','attribute-array-decode','gc-metadata-read-ahead','reusable-declarations','callback-caller-reuse','telemetry-flush-coalescing']
flags={r:get(r)['enabled'] for r in routes};seed_path='/tmp/filesync-snapshot-seeds-mode';seed=subprocess.check_output(['docker','exec',record['Id'],'cat',seed_path])
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'metadata.json').write_text(json.dumps(dict(scope='Diagnostic native walk callback counts before filtering, including the selected literal-path traversal. No wrapper hides its optional native walker. No timing comparison; no CPU profiling or wcprof. Delegate every original FS operation unchanged.',cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=module,text=True).strip(),telemetry=True,normal_gc=True),indent=2)+'\n')
try:
    assert not get('wcprof/enabled')['global_enabled'] and not get('snapshot-collection')['deferred']
    for r in routes:mode(r,r in ['batch-metadata','attribute-array-decode','reusable-declarations'])
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=b'on\n',check=True)
    idle('filesync-counts')
    edit.write_bytes(original+('\n// Import walk visit diagnostic '+str(time.time_ns())+'\n').encode())
    (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    tick=time.monotonic()
    with (root/'command.stdout').open('w') as out,(root/'command.stderr').open('w') as err:
        p=subprocess.Popen([str(cli),'check','--module','go','--check','test','--list','--all'],cwd=source,env=env,stdout=out,stderr=err,start_new_session=True)
        try:p.wait(timeout=300)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGINT);p.wait();raise
    seconds=time.monotonic()-tick
finally:
    edit.write_bytes(original)
    for n,d in saved.items():
        if d is None:(source/n).unlink(missing_ok=True)
        else:(source/n).write_bytes(d)
    for r,v in flags.items():mode(r,v)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=seed,check=True)
listed=[s for s in (root/'command.stdout').read_text().splitlines() if s.startswith('go ')];expected=[s for s in (base/'glob-literal-prefix/full-command-paired/0-before.stdout').read_text().splitlines() if s.startswith('go ')]
rows=[json.loads(s.removeprefix('native-walk ')) for s in (root/'command.stderr').read_text().splitlines() if s.startswith('native-walk ')]
(root/'walk-counts.json').write_text(json.dumps(rows,indent=2)+'\n')
summary=dict(seconds=seconds,exit_code=p.returncode,listed_rows=len(listed),same_rows=listed==expected,native_walk_calls=len(rows),nodes=sum(x['nodes'] for x in rows),directories=sum(x['directories'] for x in rows),top_by_visits=sorted(rows,key=lambda x:x['nodes'],reverse=True)[:12])
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
assert p.returncode==0 and listed==expected and rows
