from pathlib import Path
from collections import Counter
import json
import subprocess

root=Path(__file__).parent
capture=root/'capture'
path=capture/'wcprof-complete.ndjson'
def summarize(path):
    counts=Counter();outcomes=Counter();published=[];parents={};classes={};interesting=[]
    with path.open() as stream:
        header=json.loads(next(stream));names=header['strings']
        for line in stream:
            e=json.loads(line)
            if e.get('e')!='op':continue
            cls=names[e['c']];kind=e['k'];counts[(kind,cls)]+=1
            outcomes[(kind,cls,e.get('o',''))]+=1
            parents[e['id']]=e.get('p',0)
            classes[e['id']]=(kind,cls)
            if cls=='dagql.publishResult':published.append(e.get('p',0))
            if cls in ['session.serveQuery','session.query','Artifacts.items','go:Go.packages','go:GoPackage.tests','dang.invoke']:
                interesting.append(dict(e,cls=cls))
    byclass=Counter()
    for parent in published:
        while parent and parent in classes:
            kind,cls=classes[parent]
            if kind in ['call_exec','call']:
                byclass[cls]+=1;break
            parent=parents.get(parent,0)
    main=max((e for e in interesting if e['cls']=='session.serveQuery'),key=lambda e:e['d']-e['s'])
    fields=['SearchResult.filePath','SearchResult.matchedLines','Artifact.items','ArtifactDimensionKey.dimensionKeys']
    return dict(header={k:v for k,v in header.items() if k!='strings'},main_query=main,publications=len(published),publications_by_field=dict(byclass),fields={f:{kind:counts[(kind,f)] for kind in ['call','call_exec']} for f in fields},outcomes=[dict(kind=k[0],field=k[1],outcome=k[2],count=v) for k,v in outcomes.items() if k[1] in fields],longest_intervals={cls:sorted([dict(id=e['id'],kind=e['k'],seconds=(e['d']-e['s'])/1e9,start=(e['s']-main['s'])/1e9,end=(e['d']-main['s'])/1e9) for e in interesting if e['cls']==cls],key=lambda e:e['seconds'],reverse=True)[:4] for cls in ['Artifacts.items','go:Go.packages','go:GoPackage.tests']})
results={label:summarize(path) for label,path in [('selected_control_capture',root.parent/'config-content-declarations/capture/wcprof-complete.ndjson'),('candidate_capture',path)]}
(root/'wcprof-derived.json').write_text(json.dumps(results,indent=2)+'\n')
op=results['candidate_capture']['main_query']['id']
command=['/tmp/rust-cache-wcprof-report-current','-view','critpath','-op',str(op),'-top','35','-depth','8','-limit','100',str(path)]
with (capture/'main-critical.txt').open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
(root/'wcprof-analysis-command.json').write_text(json.dumps(dict(command=command,exit_code=result.returncode),indent=2)+'\n')
assert result.returncode==0
for label,row in results.items():
    print(label,'publications',row['publications'],'fields',row['fields'],flush=True)
