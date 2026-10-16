from pathlib import Path
import sys
sys.argv=[sys.argv[0],'--output',str(Path(__file__).parent/'sort-isolation')]
exec(Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py').read_text().split('fixtures = [f for f')[0])

source=Path('/tmp/dagger-go-real-repository-main')
saved={name:(source/name).read_bytes() if (source/name).exists() else None for name in ['dagger.toml','dagger.lock']}
rows=[]
try:
    for label,module in [('before','/tmp/dagger-go-package-test-discovery'),('append','/tmp/dagger-go-ordered-discovery-inputs')]:
        (source/'dagger.toml').write_text('[modules.gomod]\nsource = "'+module+'/gomod"\n')
        command=[str(cli),'api','call','gomod','at','--path=.','own-files','--glob=*.go']
        idle(label);a=heap();tick=time.monotonic()
        with (root/(label+'.log')).open('w') as out:
            try:r=subprocess.run(command,cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=40);code=r.returncode
            except subprocess.TimeoutExpired:code=124
        b=heap();row=dict(label=label,seconds=time.monotonic()-tick,exit_code=code,allocated_bytes=b['TotalAlloc']-a['TotalAlloc'],command=command)
        rows.append(row);(root/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(row,flush=True)
finally:
    for name,data in saved.items():
        if data is None:(source/name).unlink(missing_ok=True)
        else:(source/name).write_bytes(data)
