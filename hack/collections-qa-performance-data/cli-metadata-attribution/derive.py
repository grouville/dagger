from pathlib import Path
import json,hashlib,statistics
P=Path(__file__).resolve().parent;R=P.parent/'cloud-v1/results.json';rows=json.loads(R.read_text());events=json.loads((P/'shutdown/numeric-phases.json').read_text())['rows']
safe=[]
for i,r in enumerate(rows):
 phases={e['phase']:e['duration_ms']for e in events if e['command_ordinal']==i and e['client_is_main']};assert len(phases)==5,(i,phases)
 ms=r['seconds']*1000
 handler=next(e for e in events if e['command_ordinal']==i and e['client_is_main'] and e['phase']=='shutdown handler total')
 pre_handler=handler['end_from_command_start_ms']-handler['duration_ms'];post_handler=-handler['end_relative_to_command_exit_ms']
 assert pre_handler>=0 and post_handler>=0
 safe.append(dict(command_ordinal=i,phase=r['phase'],index=r['index'],flow=r['flow'],variant=r['variant'],production=r['production'],correct=r['correct'],exit_code=r['exit_code'],cli_ms=ms,pre_handler_ms=pre_handler,post_handler_to_exit_ms=post_handler,phases_ms=phases,cli_outside_handler_ms=ms-phases['shutdown handler total'],engine_cpu_seconds=r['engine_cpu_seconds'],engine_written_bytes=r['engine_written_bytes'],host_psi_delta_us=r['host_psi_delta_us'],counter_bracket_seconds=r['counter_bracket_seconds'],input_sha256=r['input_sha256'],stdout_sha256=r['stdout_sha256']))
pairs=[]
for phase,flow,index in dict.fromkeys((r['phase'],r['flow'],r['index'])for r in safe):
 rr=[r for r in safe if(r['phase'],r['flow'],r['index'])==(phase,flow,index)]
 if len(rr)!=2:continue
 b=next(r for r in rr if r['variant']=='baseline');c=next(r for r in rr if r['variant']=='candidate')
 assert b['input_sha256']==c['input_sha256'] and b['stdout_sha256']==c['stdout_sha256'] and b['correct']and c['correct']
 pairs.append(dict(phase=phase,flow=flow,index=index,order=[r['variant']for r in rr],baseline_ordinal=b['command_ordinal'],candidate_ordinal=c['command_ordinal'],cli_delta_ms=c['cli_ms']-b['cli_ms'],pre_handler_delta_ms=c['pre_handler_ms']-b['pre_handler_ms'],post_handler_delta_ms=c['post_handler_to_exit_ms']-b['post_handler_to_exit_ms'],handler_delta_ms=c['phases_ms']['shutdown handler total']-b['phases_ms']['shutdown handler total'],cloud_flush_delta_ms=c['phases_ms']['flush session Cloud telemetry']-b['phases_ms']['flush session Cloud telemetry'],outside_handler_delta_ms=c['cli_outside_handler_ms']-b['cli_outside_handler_ms']))
comparisons={}
for phase,flow in dict.fromkeys((r['phase'],r['flow'])for r in safe):
 rs=[r for r in safe if r['phase']==phase and r['flow']==flow]
 if not any(r['variant']=='candidate'for r in rs):continue
 q={}
 for v in['baseline','candidate']:
  vr=[r for r in rs if r['variant']==v]
  q[v]=dict(count=len(vr),cli_median_ms=statistics.median(r['cli_ms']for r in vr),pre_handler_median_ms=statistics.median(r['pre_handler_ms']for r in vr),post_handler_median_ms=statistics.median(r['post_handler_to_exit_ms']for r in vr),outside_handler_median_ms=statistics.median(r['cli_outside_handler_ms']for r in vr),cpu_median_seconds=statistics.median(r['engine_cpu_seconds']for r in vr),phase_medians_ms={k:statistics.median(r['phases_ms'][k]for r in vr)for k in vr[0]['phases_ms']})
 ps=[r for r in pairs if r['phase']==phase and r['flow']==flow]
 q['paired_medians_ms']={k:statistics.median(r[k]for r in ps)for k in['cli_delta_ms','pre_handler_delta_ms','handler_delta_ms','post_handler_delta_ms','cloud_flush_delta_ms','outside_handler_delta_ms']};comparisons[phase+'/'+flow]=q
result=dict(scope='Offline attribution of 33 attempted commands: 32 correct and one baseline collection failure. No new CLI/Cloud commands.',results_sha256=hashlib.sha256(R.read_bytes()).hexdigest(),rows=safe,pairs=pairs,comparisons=comparisons,limits=['Only main-client shutdown phases used for foreground subtraction.','Outside-handler residual includes query, setup, output and CLI cleanup; it is not pure query time.','Cloud flush includes export drains and the token-refresh gate, not HTTP/server attribution.','Three warm pairs per flow/configuration, with local block before Cloud block.','Resource counter brackets surround CLI time and can include background work.','Same source bytes reused in fresh-input pair; second variant can reuse downstream results, so not independent cold edit costs.'])
(P/'numeric-attribution.json').write_text(json.dumps(result,indent=2)+'\n')
for phase in['local-warm','cloud-warm']:
 for flow in['core','module']:
  print(phase,flow,json.dumps(comparisons[phase+'/'+flow]))
for p in pairs:
 if p['phase']=='cloud-warm':print(json.dumps(p))
