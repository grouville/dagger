"""Sanitized numeric reduction after the complete local-only trial restores state."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,hashlib,json,statistics
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def merge(xs):
 result=[]
 for a,b in sorted(xs):
  if result and a<=result[-1][1]:result[-1][1]=max(b,result[-1][1])
  else:result.append([a,b])
 return result
def union(xs):return sum(b-a for a,b in merge(xs))/1e6

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',default='results-v1');a=p.parse_args();run=HERE/a.run_dir;out=HERE/(a.run_dir+'-evidence');assert not out.exists()
 rows=json.loads((run/'results.json').read_text());restore=json.loads((run/'restoration.json').read_text());assert len(rows)==72 and all(r['correct']for r in rows)
 assert restore['fixtures_restored'] and restore['engine_original_restored'] and restore['engine_stopped'] and restore['cloud_commands']==0
 out.mkdir()
 def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
 write('samples.json',rows);write('restoration.json',restore)
 summaries=[];pairs=[]
 for phase,flow in sorted({(r['phase'],r['flow'])for r in rows if r['phase']in('warm','fresh-edit')}):
  group=[r for r in rows if(r['phase'],r['flow'])==(phase,flow)]
  s={'phase':phase,'flow':flow,'samples_per_variant':2}
  for variant in ('baseline','candidate'):
   vs=[r for r in group if r['variant']==variant];assert len(vs)==2
   s[variant]={'seconds':[r['seconds']for r in vs],'median_seconds':statistics.median(r['seconds']for r in vs),'cli_tree_cpu_seconds':[r['process_tree_user_seconds']+r['process_tree_system_seconds']for r in vs],'engine_cpu_seconds':[r['engine_cpu_seconds']for r in vs],'file_visible_seconds':[r['file_visible_seconds']for r in vs]}
  s['median_delta_ms']=(s['candidate']['median_seconds']-s['baseline']['median_seconds'])*1000
  s['median_percent_change']=100*(s['candidate']['median_seconds']/s['baseline']['median_seconds']-1)
  summaries.append(s)
  for pair_index,(b,c)in enumerate(((0,1),(3,2))):
   base=next(r for r in group if r['block']==b);candidate=next(r for r in group if r['block']==c)
   pairs.append({'phase':phase,'flow':flow,'pair_index':pair_index,'block_order':'AB'if pair_index==0 else'BA','baseline_seconds':base['seconds'],'candidate_seconds':candidate['seconds'],'delta_ms':1000*(candidate['seconds']-base['seconds'])})
 write('summary.json',{'scope':'exploratory n2 per variant, ABBA blocks on one retained volume, Cloud disabled','groups':summaries});write('paired-values.json',pairs)
 # Every fresh edit is independently unique for its actual changed input.
 edits=[r for r in rows if r['phase']=='fresh-edit']
 for flow,key in [('call','input_sha256'),('generate','input_sha256'),('check','native_module_sha256'),('checks','app_main_sha256')]:
  vs=[r[key]for r in edits if r['flow']==flow];assert len(vs)==len(set(vs))==4
 write('correctness.json',{'commands':72,'expected_successes':70,'expected_sentinel_failures':2,'correct_outcomes':sum(r['correct']for r in rows),'all_unique_edit_inputs':True,'exact_greetings_check_rows':14,'native_standard_check':True,'native_generation':'ordinary Dang generator, not Go/TS SDK code generation','greetings_real_selected_check':'TestFormatResponse selected with --generated=false; two correctness-only smokes, not an execution speed estimate','ordinary_profiles':False,'separate_profiles':2,'not_measured':['fresh-volume cold','service up','Cloud'],'source_and_outputs_restored':True})
 profiles={}
 for i,row in enumerate(rows):
  if not row['profile']:continue
  d=run/f"{i:02d}-{row['block']}-{row['phase']}-{row['flow']}-{row['variant']}";path=d/'run.wcprof.private'
  with path.open()as f:header=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
  ops=[o for o in ops if o.get('e')=='op'];by_id={o['id']:o for o in ops};strings=header['strings'];origin=min(o['s']for o in ops)
  def name(o):return strings[o.get('c',0)]
  def span(o):return(o['s'],o['d'])
  def facts(oset):return {'count':len(oset),'inclusive_sum_ms':sum(o['d']-o['s']for o in oset)/1e6,'interval_union_ms':union([span(o)for o in oset]),'intervals':[{'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}for o in sorted(oset,key=lambda o:o['s'])]}
  parents=[o for o in ops if name(o)=='filesync.syncParentDirs'];hosts=[o for o in ops if o['k']=='call_exec'and name(o)=='Host.directory']
  queries=[o for o in ops if name(o)=='session.query'];per_host=[]
  for host in sorted(hosts,key=lambda o:o['s']):
   children=[]
   for parent in parents:
    cur=parent;seen=set()
    while cur and cur['id']not in seen:
     if cur['id']==host['id']:children.append(parent);break
     seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   ints=[span(o)for o in children]
   per_host.append({'start_ms':(host['s']-origin)/1e6,'host_directory_ms':(host['d']-host['s'])/1e6,'parent_sync_count':len(children),'parent_sync_union_ms':union(ints),'remaining_host_interval_ms':(host['d']-host['s'])/1e6-union(ints),'pre_parent_ms':(min(o['s']for o in children)-host['s'])/1e6 if children else None,'post_parent_ms':(host['d']-max(o['d']for o in children))/1e6 if children else None})
  phase={}
  for label,kind,cl in [('workspace_artifacts','call_exec','Workspace.artifacts'),('collection_expansion','call_exec','Artifacts.__itemsJSON'),('git_advertisements','internal','git.publicAdvertisement'),('find_roots','call_exec','Workspace.findRoots'),('workspace_file','call_exec','Workspace.file'),('workspace_glob','call_exec','Workspace.glob'),('go_modules','call_exec','go:Go.modules')]:phase[label]=facts([o for o in ops if o['k']==kind and name(o)==cl])
  go_ops=[o for o in ops if o['k']=='call_exec' and name(o) in ('go:Go.modules','Go.modules')]
  workspace_reads=[]
  for o in ops:
   if o['k']!='call_exec' or name(o) not in ('Workspace.findRoots','Workspace.file'):continue
   cur=o;seen=set();go_ancestor=None;host_children=[]
   while cur and cur['id']not in seen:
    if cur in go_ops:go_ancestor=cur;break
    seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   for h in hosts:
    cur=h;seen=set()
    while cur and cur['id']not in seen:
     if cur['id']==o['id']:host_children.append(h);break
     seen.add(cur['id']);cur=by_id.get(cur.get('p'))
   workspace_reads.append({'class':name(o),'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6,'go_modules_parent_chain_proven':go_ancestor is not None,'temporally_enclosed_by_go_modules':any(g['s']<=o['s']and o['d']<=g['d']for g in go_ops),'host_directory_child_count':len(host_children),'host_directory_child_union_ms':union([span(h)for h in host_children])})
  profiles[row['variant']]={'profile_sha256':sha(path),'schema_version':header['schema_version'],'operation_count':len(ops),'operation_kinds':dict(Counter(o['k']for o in ops)),'dropped_events':header['dropped_events'],'open_operations':len(header.get('open_ops',[])),'instrumented_cli_seconds':row['seconds'],'operation_window_ms':(max(o['d']for o in ops)-origin)/1e6,'query_union_ms':union([span(o)for o in queries]),'parent_sync':facts(parents),'host_directory':facts(hosts),'parent_sync_hosts':per_host,'phases':phase,'workspace_read_details':workspace_reads,'go_module_operations':facts(go_ops),'subtree_measurement_limit':'There is no separate subtree marker in this build. Remaining Host.directory intervals include initial stat/path resolution, subtree sync, local mirror/filter/hash work; they are not pure subtree transfer duration. Nested/overlapping intervals must not be added to predict CLI savings.'}
  assert header['dropped_events']==0 and not header.get('open_ops') and parents
 write('profiles.json',profiles)
 manifest=json.loads((HERE/'frozen-builds.json').read_text());provenance=json.loads((run/'provenance.json').read_text())
 write('provenance.json',{'source_head':manifest['source_head'],'original_engine_ancestry_sha256':manifest['original_baseline_engine_sha256'],'binary_sha256':{v:{k:manifest[v][k]['sha256']for k in('cli','engine')}for v in('baseline','candidate')},'same_profile_marker':manifest['wcprof_marker'],'frozen_manifest_sha256':sha(HERE/'frozen-builds.json'),'driver_sha256':sha(run/'driver.py.txt'),'results_sha256':sha(run/'results.json'),'profile_flags_only_in_two_diagnostic_commands':True,'cache_boundary':provenance['cache_boundary'],'edit_boundary':provenance['edit_boundary'],'limits':provenance['limits'],'ambient_width_caveat':provenance['ambient_width_caveat'],'cloud_commands':0,'notes':['This uses the frozen experimental SDK/Dang stack with common f864 engine ancestry; not unmodified main.','Two observations per variant cannot establish stable percentile distributions or causality for small changes.','CPU/I/O snapshots bracket commands and include engine background work; they do not exactly isolate foreground CPU.','The inherited /tmp directory contains about6000 entries and can amplify parent enumeration costs.']})
 lines=['The local-only trial completed72/72 expected outcomes. Both fixtures and the original engine binary were restored, and the owned engine is stopped. No Cloud command ran.','', 'The two variants use the same frozen SDK/Dang stack and retained engine volume. ABBA blocks have explicit primers; each flow has only two ordinary observations per variant. These are exploratory timings, not reliable percentiles.','', '| Phase / command | Baseline samples (s) | Candidate samples (s) | Median change |','| --- | --- | --- | ---: |']
 for s in summaries:
  lines.append(f"| {s['phase']} / {s['flow']} | {' / '.join(f'{n:.3f}'for n in s['baseline']['seconds'])} | {' / '.join(f'{n:.3f}'for n in s['candidate']['seconds'])} | {s['median_delta_ms']:+.1f} ms ({s['median_percent_change']:+.1f}%) |")
 lines+=['','Fresh native call and generate inputs, fresh native Dang source comments for standard checks, and fresh greetings Go source comments for listing were independently unique. Native warm generation leaves an already-current output in place. Edit generation starts from the previous output bytes and verifies newly generated bytes; its file visibility is separate from full CLI exit. Export removes only its tracked destination and verifies the copied input. Standard native check additionally has a fail/restore sentinel.','', 'The real greetings TestFormatResponse check passed once per variant, with `--generated=false`; these are correctness smokes on retained caches, not a measurement of repeated test-body execution. Native generation is one ordinary Dang Changeset generator, not Go/TypeScript SDK code generation. Fresh-volume cold, service up and Cloud export were not tested.','', 'The parent profile marker is identical in both engine builds and inactive during ordinary timings. Separate diagnostic profiles give:','', '| Diagnostic quantity | Baseline | Candidate |','| --- | ---: | ---: |']
 for title,fn in [('CLI exit (ms)',lambda p:p['instrumented_cli_seconds']*1000),('Query interval union (ms)',lambda p:p['query_union_ms']),('Parent-sync count',lambda p:p['parent_sync']['count']),('Parent-sync inclusive sum (ms)',lambda p:p['parent_sync']['inclusive_sum_ms']),('Parent-sync interval union (ms)',lambda p:p['parent_sync']['interval_union_ms']),('Host.directory interval union (ms)',lambda p:p['host_directory']['interval_union_ms'])]:lines.append(f"| {title} | {fn(profiles['baseline']):.2f} | {fn(profiles['candidate']):.2f} |")
 lines+=['','Inclusive durations overlap. The interval union avoids counting concurrent parent synchronization twice, but it is still not the complete critical path and cannot simply be subtracted from CLI wall time. There is no distinct subtree marker: the Host.directory remainder includes path/stat resolution, actual subtree transfer and engine mirror/hash work. Per-import spans are retained numerically in profiles.json.','', 'This host has roughly6000 entries in /tmp because of accumulated test artifacts. That makes removal of sibling enumeration especially relevant here; do not promise the same saving for a small user filesystem. Synthetic width measurements separately establish the algorithmic improvement.','', 'The explicit operation retains normal filesync authority, fresh stats, old-client filter fallback and directory-only packets. Generic filtering stays unchanged. Point-lookup case/access behavior and existing concurrent-mutation/filter error handling are documented in the separate source review; Windows runtime parity remains untested. No result demonstrates500ms across all Dagger UX.']
 (out/'report.md').write_text('\n'.join(lines)+'\n')
 for name in ('runtime.py','freeze_builds.py','analyze.py'):(out/name).write_bytes((HERE/name).read_bytes())
 write('archive-allowlist.json',{'files':['report.md','samples.json','summary.json','paired-values.json','correctness.json','profiles.json','provenance.json','restoration.json','runtime.py','freeze_builds.py','analyze.py'],'exclude':'No raw stdout/stderr/wcprof, container IDs, credential/config files, or raw source input contents.'})
 print(json.dumps({'evidence':str(out),'commands':len(rows),'groups':len(summaries),'profile_counts':{v:p['parent_sync']['count']for v,p in profiles.items()}}))
if __name__=='__main__':main()
