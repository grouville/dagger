from pathlib import Path
import collections
import json
import subprocess

root=Path(__file__).parent
paths={'before':Path('/tmp/rust-cache-sipsma-review/go-local-discovery-profile/original'), 'after':root/'profile'}
results={}
for arm,path in paths.items():
    with (path/'wcprof-complete.ndjson').open() as stream:
        header=json.loads(next(stream)); strings=header['strings']; ops={}
        for line in stream:
            event=json.loads(line)
            if event['e']=='op': ops[event['id']]=event
    classes=collections.defaultdict(list)
    for op in ops.values(): classes[strings[op['c']]].append(op)
    names=['dang.evalSource','dang.openSchema','dang.decodeSchema','dang.selfTypes','dang.prepareSource','dang.runSource','dang.runSource.parse','dang.runSource.infer','dang.runSource.evaluate','dang.apiRequest']
    results[arm]={name:dict(count=len(classes[name]),summed_seconds=sum((op['d']-op['s'])/1e9 for op in classes[name])) for name in names}
    queries=sorted(classes['session.serveQuery'],key=lambda op:op['d']-op['s'],reverse=True)
    results[arm]['recorder']=dict(events=header['event_count'],dropped=header['dropped_events'],open=len(header.get('open_ops',[])))
    if arm=='after':
        with (path/'main-critical.txt').open('w') as out:
            subprocess.run(['/tmp/rust-cache-wcprof-report','-view','critpath','-op',str(queries[0]['id']),str(path/'wcprof-complete.ndjson')],stdout=out,stderr=subprocess.STDOUT,check=True)
    print(arm,json.dumps(results[arm]),flush=True)
(root/'phase-comparison.json').write_text(json.dumps(results,indent=2)+'\n')
assert results['after']['dang.openSchema']['count']<results['before']['dang.openSchema']['count']
assert results['after']['dang.decodeSchema']['count']<results['before']['dang.decodeSchema']['count']
