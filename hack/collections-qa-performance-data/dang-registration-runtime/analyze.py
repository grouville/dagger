#!/usr/bin/env python3
"""Numeric-only reduction of the completed registration matrix; raw files private."""
from pathlib import Path
import collections,hashlib,json,statistics
H=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=json.loads((H/'results-numeric.json').read_text())
assert len(rows)==36 and all(r['correct']for r in rows)
summary=json.loads((H/'summary-v1.json').read_text())
restorations=[json.loads((H/f'block-{b}/lifecycle-restoration.json').read_text())for b in range(6)]
assert all(not r['cleanup_error_types']and all(r[k]for k in ('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))for r in restorations)
assert all(summary['fixtures_restored'].values())and summary['original_public_fixture_untouched']
def samples(xs):
 vals=[r['seconds']for r in xs]
 return {'n':len(vals),'seconds':vals,'median_seconds':statistics.median(vals),'minimum_seconds':min(vals),'maximum_seconds':max(vals),'engine_cpu_seconds':[r['engine_cpu_seconds']for r in xs],'engine_written_bytes':[r['engine_written_bytes']for r in xs],'host_io_full_pressure_seconds':[r['host_psi_delta_us']['io']['full']/1e6 for r in xs],'process_tree_cpu_seconds':[r['process_tree_user_seconds']+r['process_tree_system_seconds']for r in xs]}
strata={}
for phase,flow in [('warm','checks'),('warm','artifacts'),('fresh-comment','checks')]:
 key=phase+'-'+flow
 strata[key]={v:samples([r for r in rows if r['variant']==v and r['phase']==phase and r['flow']==flow])for v in ('baseline','candidate')}
 a,b=(strata[key][v]['median_seconds']for v in ('baseline','candidate'))
 strata[key].update(median_delta_seconds=b-a,median_reduction_percent=100*(a-b)/a)
comments=[r['app_main_sha256']for r in rows if r['phase']=='fresh-comment']
assert len(comments)==len(set(comments))==6
controls=[{k:r[k]for k in ('global_index','variant','flow','phase','seconds','exit_code','correct','file_visible_seconds','output_already_current')}for r in rows if r['phase']in ('version-control','negative-control','restored-control','fresh-input-control')]
result={'inputs_sha256':sha(H/'frozen-runtime-inputs.json'),'results_sha256':sha(H/'results-numeric.json'),'validated_commands':len(rows),'phase_counts':dict(collections.Counter(r['phase']for r in rows)),'strata':strata,'first_demand_controls_excluded_from_warm_medians':controls,'novel_comment_hashes_unique':True,'cleanup_and_restoration_passed':True,'cloud_commands':0,'scope':'Current-production 4f2 and ordinary dependencies both arms; only owned registration metadata snapshot differs. Four correlated ABBA blocks. n2 warm/n3 comments is a bounded acceptance gate, not a distribution. Native generation and strict HTTP checks have no execution-specific primers. Profile and primer latencies excluded.'}
(H/'ordinary-summary.json').write_text(json.dumps(result,indent=2)+'\n')
LABELS=['session.query','Workspace.artifacts','Artifacts.__itemsJSON','ModuleSource.asModule','dang.invoke','dang.selfTypes','dang.runSource','dang.objectDirectives','session.modulesLoad','session.schemaBuild','schema.forkPrepared','git.publicAdvertisement','exec.processRun']
def intervals_union(xs):
 merged=[]
 for a,b in sorted(xs):
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 return sum(b-a for a,b in merged)/1e6
def stats(xs):return {'count':len(xs),'sum_ms':sum(o['d']-o['s']for o in xs)/1e6,'union_ms':intervals_union((o['s'],o['d'])for o in xs),'maximum_ms':max([o['d']-o['s']for o in xs],default=0)/1e6,'errors':sum(o.get('o')=='error'for o in xs)}
profiles={}
for variant,b in [('baseline',4),('candidate',5)]:
 row=next(r for r in rows if r['variant']==variant and r['profile'])
 path=H/f'block-{b}'/f'{row["index"]:02d}-{row["label"]}'/'run.wcprof.private'
 assert sha(path)==row['profile_sha256']
 with path.open()as f:header=json.loads(next(f));events=[json.loads(line)for line in f if line.strip()]
 ops=[o for o in events if o.get('e')=='op'];name=lambda o:header['strings'][o.get('c',0)]
 selected={n:[o for o in ops if name(o)==n and(n not in ('Workspace.artifacts','Artifacts.__itemsJSON','ModuleSource.asModule')or o['k']=='call_exec')]for n in LABELS}
 epoch=header['epoch_unix_nano']
 outside=[o for o in ops if epoch+o['s']<row['started_unix_ns']or epoch+o['d']>row['exited_unix_ns']]
 metadata=selected['dang.selfTypes']+selected['dang.objectDirectives']
 profiles[variant]={'profile_sha256':sha(path),'profiled_cli_seconds':row['seconds'],'completed_operations':len(ops),'open_operations':len(header.get('open_ops',[])),'dropped_events':header['dropped_events'],'completed_operations_outside_cli_bracket':len(outside),'phases':{n:stats(xs)for n,xs in selected.items()},'registration_metadata_phases_union':stats(metadata),'metadata_intervals_ms':[{'phase':name(o),'start_ms':(epoch+o['s']-row['started_unix_ns'])/1e6,'duration_ms':(o['d']-o['s'])/1e6}for o in sorted(metadata,key=lambda o:o['s'])]}
(H/'profile-numeric.json').write_text(json.dumps({'profiles':profiles,'scope':'One separately primed profile per engine, excluded from ordinary medians. Inclusive phases overlap; sums/unions are not additive savings. No raw identities, module source names, arguments or logs.'},indent=2)+'\n')
print(json.dumps({'strata':strata,'profiles':{v:{'open':p['open_operations'],'dropped':p['dropped_events'],'outside':p['completed_operations_outside_cli_bracket'],'metadata':p['registration_metadata_phases_union'],'phases':{n:p['phases'][n]for n in ['Workspace.artifacts','Artifacts.__itemsJSON','dang.selfTypes','dang.objectDirectives','dang.runSource']}}for v,p in profiles.items()}},indent=2))
