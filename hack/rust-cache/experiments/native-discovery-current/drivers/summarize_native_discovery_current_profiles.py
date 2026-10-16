from pathlib import Path
import collections
import json

root=Path('/tmp/rust-cache-sipsma-review/native-discovery-current/profiles')
summary={}
for path in sorted(root.glob('*.ndjson')):
    with path.open() as stream:
        header=json.loads(next(stream))
        operations=[json.loads(line) for line in stream]
    assert not header['dropped_events'] and not header.get('open_ops'),path.name
    names=header['strings']
    selected=[]
    aggregate=collections.defaultdict(lambda:dict(count=0,total_ms=0))
    executions=[]
    for op in operations:
        if op.get('e')!='op' or 'd' not in op:
            continue
        kind=op.get('k')
        cls=names[op.get('c',0)]
        ms=(op['d']-op['s'])/1e6
        row=dict(kind=kind,cls=cls,ms=ms,id=op['id'] if 'id' in op else op.get('i'))
        key=str(kind)+' '+cls
        aggregate[key]['count']+=1
        aggregate[key]['total_ms']+=ms
        if kind=='exec':
            executions.append(row)
        if kind=='call_exec' and cls in ['rust:Rust.packages','Directory.treeFingerprint','Host.directory','ModuleSource.asModule']:
            selected.append(row)
    summary[path.stem]=dict(dropped_events=header['dropped_events'],open_ops=header.get('open_ops',0),
                            selected=selected,exec_count=len(executions),executions=executions,
                            top_aggregate_operations=sorted(
                                [dict(cls=k,**v) for k,v in aggregate.items()],
                                key=lambda v:v['total_ms'],reverse=True)[:30],
                            aggregate_duration_is_not_additive_wall_time=True)
(root/'operation-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for label,data in summary.items():
    print(label,'execs',data['exec_count'],
          [(r['cls'],round(r['ms'],1)) for r in data['selected'] if r['cls'] in ['rust:Rust.packages','Directory.treeFingerprint']])
