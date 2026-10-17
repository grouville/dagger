from pathlib import Path
import collections
import datetime
import json
import subprocess

root=Path(__file__).parent
path=root/'profile'
with (path/'wcprof-complete.ndjson').open() as stream:
    header=json.loads(next(stream)); strings=header['strings']; ops={}; links=[]
    for line in stream:
        event=json.loads(line)
        if event['e']=='op':ops[event['id']]=event
        elif event['e']=='link' and event.get('lk')=='nested_client':links.append(event)

def cls(op):return strings[op.get('c',0)]
def duration(op):return (op['d']-op['s'])/1e9
nested={link['p']:strings[link['i']] for link in links}
queries=collections.defaultdict(list)
for op in ops.values():
    if cls(op)=='session.serveQuery':queries[strings[op.get('cl',0)]].append(op)
for values in queries.values():values.sort(key=lambda op:op['s'])

rows=[]
for api in ops.values():
    if cls(api)!='dang.apiRequest':continue
    ancestor=ops.get(api.get('p'))
    while ancestor is not None and ancestor['id'] not in nested:ancestor=ops.get(ancestor.get('p'))
    client=nested.get(ancestor['id']) if ancestor else None
    candidates=[q for q in queries.get(client,[]) if q['s']>=api['s'] and q['d']<=api['d']]
    row=dict(api_id=api['id'],seconds=duration(api),client_id=client,contained_queries=len(candidates))
    if len(candidates)==1:
        query=candidates[0]
        row.update(query_id=query['id'],query_seconds=duration(query),outside_query_seconds=duration(api)-duration(query))
    rows.append(row)
rows.sort(key=lambda r:r['seconds'],reverse=True)
matched=[r for r in rows if r['contained_queries']==1]
summary=dict(api_requests=len(rows),nested_client_links=len(links),exactly_one_contained_query=len(matched),
    no_contained_query=sum(r['contained_queries']==0 for r in rows),ambiguous=sum(r['contained_queries']>1 for r in rows),
    summed_api_seconds=sum(r['seconds'] for r in matched),summed_query_seconds=sum(r['query_seconds'] for r in matched),
    summed_outside_query_seconds=sum(r['outside_query_seconds'] for r in matched),
    interpretation='Correlated by the recorded nested-client identity and a unique query contained in its API interval. Sums overlap across invocations and are not critical-path time or available savings.',largest=rows[:20])
(path/'api-query-correlation.json').write_text(json.dumps(summary,indent=2)+'\n')
for index,row in enumerate(matched[:3]):
    with (path/f'api-{index}-backend-critical.txt').open('w') as out:
        subprocess.run(['/tmp/rust-cache-wcprof-report','-view','critpath','-op',str(row['query_id']),str(path/'wcprof-complete.ndjson')],stdout=out,stderr=subprocess.STDOUT,check=True)

# Compare the long publication intervals with the bounded snapshot-maintenance history.
gc=json.loads((root/'after-profile-snapshot-collection.json').read_text())['events']
def ns(timestamp):return int(datetime.datetime.fromisoformat(timestamp.replace('Z','+00:00')).timestamp()*1e9)
pubs=sorted((op for op in ops.values() if cls(op)=='dagql.publishResult'),key=duration,reverse=True)
publication=[]
for op in pubs[:20]:
    start=header['epoch_unix_nano']+op['s']; end=header['epoch_unix_nano']+op['d']
    overlap=[event for event in gc if ns(event['start'])<end and ns(event['end'])>start]
    parent=ops.get(op.get('p'))
    publication.append(dict(id=op['id'],parent_class=cls(parent) if parent else None,seconds=duration(op),
        unix_start_ns=start,unix_end_ns=end,snapshot_maintenance_overlap=overlap))
(path/'long-publication-maintenance.json').write_text(json.dumps(publication,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='largest'},indent=2))
print('largest API',rows[:3])
print('largest publication',publication[:3])
