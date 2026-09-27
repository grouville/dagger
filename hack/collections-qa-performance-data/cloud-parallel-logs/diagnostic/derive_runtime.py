#!/usr/bin/env python3
"""Derive anonymous numeric evidence from the completed passive diagnostic."""
import collections, hashlib, json, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parent
RUN=ROOT/'runtime-v1'
OUT=ROOT/'runtime-evidence'
OUT.mkdir(exist_ok=True)
rows=json.loads((RUN/'results.json').read_text())
dirs=sorted(x for x in RUN.iterdir() if x.is_dir() and x.name[:2].isdigit())
assert len(rows)==len(dirs)==8
HTTP={'cloud.traces','cloud.logs','cloud.metrics','cloud.other'}
PHASES=['engine.cloud.session.force_flush','engine.cloud.spans.force_flush','engine.cloud.logs.force_flush','engine.cloud.logs.payload.force_flush','engine.cloud.logs.records.force_flush','engine.cloud.token_gate.stop','engine.cloud.token_gate.wait','engine.cloud.token_refresh','engine.cloud.token_file.read','engine.cloud.token_exchange','engine.cloud.token_file.write','engine.schema.base_lookup','engine.schema.base_lock','engine.schema.base_build','engine.schema.view_state','engine.schema.view_lock','engine.schema.view_build','engine.schema.typedef_build','engine.schema.server_fork','engine.schema.fork','engine.client.runtime_initialize','engine.http.serve_query','engine.cloud.reachability.check']
def ms(x):return round(x/1e6,6)
def aggregate(events):
    out=[]
    for key,group in __import__('itertools').groupby(sorted(events,key=lambda e:(e['kind'],e.get('values',{}).get('log_class',0))),key=lambda e:(e['kind'],e.get('values',{}).get('log_class',0))):
        g=list(group);vs=[e.get('values',{}) for e in g]
        out.append(dict(kind=key[0],log_class=key[1],requests=len(g),declared_request_bytes=sum(v.get('request_content_length',0) for v in vs),records=sum(v.get('records',0) for v in vs),statuses=dict(collections.Counter(str(v.get('status',0)) for v in vs)),transport_errors=sum(v.get('transport_error',0) for v in vs),reuse=sum(v.get('connection_reused',0) for v in vs),connect_attempts=sum(v.get('connect_attempts',0) for v in vs),tls_attempts=sum(v.get('tls_attempts',0) for v in vs),connection_acquire_ms_sum=ms(sum(v.get('connection_acquire_ns',0) for v in vs)),http_ms_sum=ms(sum(e['end_ns']-e['start_ns'] for e in g)),write_to_first_byte_ms_sum=ms(sum(v['first_byte_ns']-v['wrote_request_ns'] for v in vs if 'first_byte_ns' in v and 'wrote_request_ns' in v)),response_bytes=sum(v.get('response_bytes',0) for v in vs)))
    return out
out=[]
for i,(r,d) in enumerate(zip(rows,dirs)):
    snapshots={k:json.loads((d/f'engine-{k}.json').read_text()) for k in ('before','post-exit-sample','settled')}
    s=snapshots['settled'];a=s['anchor_unix_ns'];lo=r['engine_event_first_sequence'];hi=r['engine_event_last_sequence']
    events=[e for e in s['events'] if lo<=e['sequence']<=hi]
    assert s['dropped_events']==0 and s['http_active']==0
    http=[e for e in events if e['kind'] in HTTP]
    assert len(http)==r['engine_http_requests']
    phases={}
    for kind in PHASES:
        es=[e for e in events if e['kind']==kind]
        if es:phases[kind]=[dict(start_cli_ms=ms(a+e['start_ns']-r['started_unix_ns']),duration_ms=ms(e['end_ns']-e['start_ns'])) for e in es]
    flushes=[e for e in events if e['kind']=='engine.cloud.session.force_flush'];assert len(flushes)<=1
    f=flushes[0] if flushes else None
    def timing(e):
        v=e.get('values',{});x=dict(kind=e['kind'],log_class=v.get('log_class',0),records=v.get('records'),start_cli_ms=ms(a+e['start_ns']-r['started_unix_ns']),end_cli_ms=ms(a+e['end_ns']-r['started_unix_ns']),duration_ms=ms(e['end_ns']-e['start_ns']))
        if e['kind'] in HTTP:
            x.update(declared_request_bytes=v.get('request_content_length',0),status=v.get('status',0),connection_reused=v.get('connection_reused',0),connection_acquire_ms=ms(v.get('connection_acquire_ns',0)),write_to_first_byte_ms=ms(v['first_byte_ns']-v['wrote_request_ns']) if 'first_byte_ns'in v and'wrote_request_ns'in v else None,ends_after_cli_exit=a+e['end_ns']>r['exited_unix_ns'],starts_after_cli_exit=a+e['start_ns']>r['exited_unix_ns'],foreground_flush_overlap_ms=ms(max(0,min(e['end_ns'],f['end_ns'])-max(e['start_ns'],f['start_ns']))) if f else 0)
        return x
    cli=[json.loads(line) for line in (d/'timeline.jsonl').read_text().splitlines()]
    cli_anchor=next(e['unix_ns'] for e in cli if e['kind']=='anchor')
    cli_http=[e for e in cli if e['kind'] in HTTP]
    cli_phases={e['kind']:dict(start_cli_ms=ms(cli_anchor+e['start_ns']-r['started_unix_ns']),duration_ms=ms(e['end_ns']-e['start_ns'])) for e in cli if e['kind'] not in HTTP and e['kind']!='anchor' and not e['kind'].startswith('cloud.export.')}
    row=dict(row=i,variant=r['variant'],flow=r['flow'],phase=r['phase'],pair=r['index'],production=r['production'],correct=r['correct'],cli_ms=r['seconds']*1000,file_visible_ms=r['file_visible_seconds']*1000 if r.get('file_visible_seconds') is not None else None,settle_additional_ms=r['additional_observed_settle_seconds']*1000,phases=phases,cli_phases=cli_phases,engine_http=aggregate(http),cli_http=aggregate(cli_http),engine_exports=aggregate([e for e in events if e['kind'] in {'cloud.export.logs','cloud.export.traces'}]),engine_http_timeline=[timing(e) for e in sorted(http,key=lambda e:e['start_ns'])],log_admission_timeline=[timing(e) for e in sorted(events,key=lambda e:e['start_ns']) if e['kind'] in {'engine.cloud.logs.serial_wait','engine.cloud.logs.serial_export'}],http_ending_after_cli_exit=sum(a+e['end_ns']>r['exited_unix_ns'] for e in http),http_starting_after_cli_exit=sum(a+e['start_ns']>r['exited_unix_ns'] for e in http),post_exit_sample_http_active=snapshots['post-exit-sample']['http_active'],post_exit_sample_offset_ms=ms(a+snapshots['post-exit-sample']['snapshot_ns']-r['exited_unix_ns']),settled_http_active=s['http_active'],dropped_events=s['dropped_events'],engine_cpu_ms=r['engine_cpu_seconds']*1000,engine_written_bytes=r['engine_written_bytes'],engine_io_delta=r['engine_io_delta'],host_psi_delta_us=r['host_psi_delta_us'],counter_bracket_ms=r['counter_bracket_seconds']*1000)
    out.append(row)
(OUT/'numeric-evidence.json').write_text(json.dumps(out,indent=2)+'\n')
verification=dict(validated_commands=len(rows),cloud_commands=sum(r['production'] for r in rows),local_commands=sum(not r['production'] for r in rows),all_correct=all(r['correct'] for r in rows),all_settled=all(r['settled_quiet'] for r in rows),all_engine_event_drops_zero=all(r['dropped_events']==0 for r in out),all_settled_http_active_zero=all(r['settled_http_active']==0 for r in out),local_primer_engine_http_count=sum(sum(g['requests'] for g in r['engine_http']) for r in out if not r['production']),local_primer_cli_http_count=sum(sum(g['requests'] for g in r['cli_http']) for r in out if not r['production']),restoration=json.loads((RUN/'restoration.json').read_text()),runtime_source_sha256=hashlib.sha256((ROOT/'runtime.py').read_bytes()).hexdigest(),engine_manifest_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('manifest.prepared.json',)},instrumented_attribution_only=True)
(OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
for r in out:
    f=lambda k:round(max((x['duration_ms']for x in r['phases'].get(k,[])),default=0),3)
    print(r['row'],r['variant'],r['phase'],r['flow'],'CLI',round(r['cli_ms'],3),'flush',f('engine.cloud.session.force_flush'),'span',f('engine.cloud.spans.force_flush'),'logs',f('engine.cloud.logs.records.force_flush'),'HTTP',sum(g['requests']for g in r['engine_http']),'postexit',r['http_ending_after_cli_exit'],'gate',f('engine.cloud.token_gate.wait'))
print(json.dumps(verification,indent=2))
