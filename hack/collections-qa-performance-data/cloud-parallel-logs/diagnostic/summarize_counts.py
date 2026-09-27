from pathlib import Path
import json,collections,hashlib
p=Path(__file__).resolve().parent;run=p/'runtime-v1';out=p/'runtime-evidence'
rows=json.loads((out/'numeric-evidence.json').read_text()); proof=[]
def maximum(es):
 points=[]
 for e in es:points.extend([(e['start_cli_ms'],1),(e['end_cli_ms'],-1)])
 active=peak=0
 for _,delta in sorted(points,key=lambda x:(x[0],x[1])):active+=delta;peak=max(peak,active)
 assert active==0
 return peak
for r in rows:
 if not r['production']:continue
 exports={g['log_class']:g for g in r['engine_exports'] if g['kind']=='cloud.export.logs'}
 logs={g['log_class']:g for g in r['engine_http'] if g['kind']=='cloud.logs'}
 channels={}
 for label,n in [('ordinary',1),('payload',2)]:
  e=exports[n];h=logs[n]; assert e['requests']==h['requests']
  ts=[v for v in r['log_admission_timeline'] if v['kind']=='engine.cloud.logs.serial_export' and v['log_class']==n]
  assert len(ts)==h['requests']
  channels[label]=dict(requests=h['requests'],records=e['records'],declared_bytes=h['declared_request_bytes'],records_per_request=e['records']/h['requests'],maximum_concurrent_exports=maximum(ts),serial_wait_sum_ms=sum(v['duration_ms']for v in r['log_admission_timeline'] if v['kind']=='engine.cloud.logs.serial_wait'and v['log_class']==n))
 timeline=[v for v in r['log_admission_timeline'] if v['kind']=='engine.cloud.logs.serial_export']
 f=lambda k:r['phases'].get(k,[{'duration_ms':0}])[0]['duration_ms']
 proof.append(dict(variant=r['variant'],flow=r['flow'],cli_ms=r['cli_ms'],channels=channels,combined_log_maximum_concurrent_exports=maximum(timeline),total_log_records=sum(e['records']for e in exports.values()),total_log_requests=sum(h['requests']for h in logs.values()),total_log_declared_bytes=sum(h['declared_request_bytes']for h in logs.values()),total_engine_http_requests=sum(h['requests']for h in r['engine_http']),engine_http_ends_after_exit=r['http_ending_after_cli_exit'],main_flush_ms=f('engine.cloud.session.force_flush'),trace_flush_ms=f('engine.cloud.spans.force_flush'),ordinary_flush_ms=f('engine.cloud.logs.records.force_flush'),payload_flush_ms=f('engine.cloud.logs.payload.force_flush'),cli_telemetry_close_ms=r['cli_phases']['cli.telemetry_close']['duration_ms'],command_callback_ms=r['cli_phases']['cli.command']['duration_ms'],engine_cpu_ms=r['engine_cpu_ms'],engine_written_bytes=r['engine_written_bytes'],host_psi_delta_us=r['host_psi_delta_us']))
summary=dict(scope='One instrumented pair per flow; retained diagnostic volumes required first artifact-use local primers. Counts establish observed fragmentation, not ordinary wall causality.',rows=proof,all_channels_individually_serial=all(c['maximum_concurrent_exports']==1 for r in proof for c in r['channels'].values()),all_engine_connections_reused=all(h['requests']==h['reuse'] and h['connect_attempts']==h['tls_attempts']==0 for r in rows if r['production']for h in r['engine_http']),all_engine_http_status201=all(h['statuses']=={'201':h['requests']}for r in rows if r['production']for h in r['engine_http']),all_engine_transport_errors_zero=all(h['transport_errors']==0 for r in rows for h in r['engine_http']))
(out/'batch-accounting.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))
for r in proof:print(json.dumps(r))
