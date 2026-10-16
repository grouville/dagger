from collections import Counter
from pathlib import Path
import json
import subprocess

root=Path(__file__).parent/'profiles-final'
summary={}
for variant in ['before','after']:
    path=root/('rust-'+variant+'.ndjson')
    with path.open() as f:
        header=json.loads(next(f));names=header['strings']
        ops=[e for line in f if (e:=json.loads(line))['e']=='op']
    assert header['dropped_events']==0 and not header.get('open_ops')
    counts=Counter((e['k'],names[e.get('c',0)]) for e in ops)
    workload=[e for e in ops if e['k']=='exec_phase' and names[e.get('c',0)]=='exec.workload']
    query=max((e for e in ops if names[e.get('c',0)]=='session.query'),key=lambda e:e['d']-e['s'])
    summary[variant]=dict(workload_count=len(workload), engine_query_count=counts['session_phase','session.query'], argument_id_reads=counts['call','FunctionCallArgValue.id'],operations=len(ops),events=header['event_count'],
        dropped_events=header['dropped_events'],longest_engine_query_id=query['id'],
        longest_engine_query_seconds=(query['d']-query['s'])/1e9,
        executed_compiler_fields={name:n for (kind,name),n in counts.items() if kind=='call_exec' and 'RustCompiler.' in name})
    for view in ['summary','classes','critpath']:
        command=['/tmp/rust-cache-wcprof-report-current','-view',view,'-top','35','-limit','140']
        if view=='critpath':command+=['-op',str(query['id']),'-depth','12']
        with (root/f'rust-{variant}-{view}.txt').open('w') as out:
            subprocess.run(command+[str(path)],stdout=out,stderr=subprocess.STDOUT,check=True)
    go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
    for cumulative in [False,True]:
        args=[go,'tool','pprof','-top','-nodecount=35']+(['-cum'] if cumulative else [])+[str(root/f'rust-{variant}.pprof')]
        with (root/f'rust-{variant}-cpu-{"cum" if cumulative else "flat"}.txt').open('w') as out:
            subprocess.run(args,stdout=out,stderr=subprocess.STDOUT,check=True)
(root/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
