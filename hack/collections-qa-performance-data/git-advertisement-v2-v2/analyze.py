from pathlib import Path
import collections,hashlib,json
P=Path(__file__).resolve().parent
r=json.loads((P/'live-v2.json').read_text());previous=json.loads((P.parent/'git-advertisement-v2-v1/live-v1.json').read_text())
rows=r['rows'];groups={}
for x in rows:
 if x['request']['phase']=='primer':continue
 key=(x['request']['phase'],x['request']['repo']);groups.setdefault(key,{})[x['request']['protocol']]=x
pairs=[]
for (phase,repo),g in groups.items():
 if set(g)!={'v0','v2'}:continue
 a,b=g['v0'],g['v2']
 pairs.append({'phase':phase,'repo':repo,'valid_protocol_pair':a['classification']=='valid'and b['classification']=='valid'and a['git_protocol']=='v0'and b['git_protocol']=='v2','v0':{k:a[k]for k in ('index','body_bytes','body_done_ns','write_to_first_byte_ns','first_byte_to_body_done_ns','parse_ns','framing')},'v2':{k:b[k]for k in ('index','body_bytes','body_done_ns','write_to_first_byte_ns','first_byte_to_body_done_ns','parse_ns','framing')},'v2_minus_v0_body_done_ns':b['body_done_ns']-a['body_done_ns'],'v2_minus_v0_first_byte_wait_ns':b['write_to_first_byte_ns']-a['write_to_first_byte_ns']})
summary={'scope':'One standalone HTTP/1.1 socket per trial; public repository pairs are distinct targets, not repeated samples of a single distribution. Primers excluded from pairs. No engine/HTTP2/authorization/cache inference.','prior_failed_trial_attempts':len(previous['rows']),'current_attempts':len(rows),'total_attempts':len(rows)+len(previous['rows']),'current_completed':r['finished'],'current_stop':r['stop_reason'],'phase_counts':dict(collections.Counter(x['request']['phase']for x in rows)),'status_counts':dict(collections.Counter(str(x['status'])for x in rows)),'classification_counts':dict(collections.Counter(x['classification']for x in rows)),'framing_counts':dict(collections.Counter(x.get('framing','')for x in rows)),'all_after_first_reused':all(x['reused_connection']for x in rows[1:]),'total_body_bytes':r['total_body_bytes'],'pairs':pairs,'cloud_requests':0}
assert summary['total_attempts']<=24
(P/'numeric-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['The table excludes both new connection primers. Each row is one ordered pair; seven different repositories are not pooled into a latency distribution. Values are milliseconds, except bytes.','', '| Repo | Phase | Order | v0 first byte | v2 first byte | v0 body complete | v2 body complete | Bytes v0 / v2 |','| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
for p in pairs:
 a,b=p['v0'],p['v2'];lines.append(f"| {p['repo']} | {p['phase']} | {'0→2' if a['index']<b['index'] else '2→0'} | {a['write_to_first_byte_ns']/1e6:.3f} | {b['write_to_first_byte_ns']/1e6:.3f} | {a['body_done_ns']/1e6:.3f} | {b['body_done_ns']/1e6:.3f} | {a['body_bytes']} / {b['body_bytes']} |")
(P/'pairs.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in summary.items()if k!='pairs'},indent=2))
