#!/usr/bin/env python3
"""Offline safe numeric reduction; no engine calls, secrets or raw records retained."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,statistics
P=Path(__file__).resolve().parent
BASE=Path('/tmp/collections-perf/go-base-address-timing-v1/analyze.py')
spec=importlib.util.spec_from_file_location('fixed_profile_reducer',BASE);profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def profile_details(path):
 result=profile.reduce_profile(path)
 with path.open()as f:head=json.loads(next(f));ops=[v for line in f if line.strip()for v in[json.loads(line)]if v.get('e')=='op']
 name=lambda o:head['strings'][o.get('c',0)];byid={o['id']:o for o in ops}
 catalog=next(o for o in ops if name(o)=='Workspace.artifacts'and o['k']=='call_exec');expansion=next(o for o in ops if name(o)=='Artifacts.__itemsJSON'and o['k']=='call_exec')
 def query(o):
  while name(o)!='session.query':o=byid[o['p']]
  return o
 cq,eq=query(catalog),query(expansion)
 main=[o for o in ops if name(o)=='session.query'and o.get('cl')==cq.get('cl')]
 origin=min(o['s']for o in ops)
 result['projection_boundary']={'main_client_queries':len(main),'catalog_and_expansion_same_query':cq['id']==eq['id'],'catalog_to_expansion_ms':(expansion['s']-catalog['d'])/1e6,'main_query_intervals':[{'ordinal':i,'start_ms_relative_first_op':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}for i,o in enumerate(sorted(main,key=lambda o:o['s']))]}
 allowed=('Artifacts.id','Query.node','Module._implementationScoped','session.query','session.serveQuery','session.schemaBuild','session.modulesLoad','session.workspaceLoad')
 result['fixed_projection_counts']={label:sum(name(o)==label for o in ops)for label in allowed}
 return result,Counter(name(o)for o in ops if o['k']=='call_exec')
def main():
 rows=json.loads((P/'results-numeric.json').read_text());summary=json.loads((P/'summary-v1.json').read_text());restored=json.loads((P/'results-v1/lifecycle-restoration.json').read_text())
 assert len(rows)==38 and all(r['correct']for r in rows)and restored['validated_commands']==38 and not restored['cleanup_error_types']
 assert all(restored[k]for k in('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))
 assert all(summary['copied_fixtures_restored'].values())and all(summary['original_fixtures_untouched'].values())
 out=P/'evidence-v1';assert not out.exists();out.mkdir();groups=[]
 for phase,flow in [('warm','checks'),('warm','artifacts'),('warm','generators'),('fresh-comment','checks')]:
  filtered=[r for r in rows if r['phase']==phase and r['flow']==flow]
  values={v:[r['seconds']*1000 for r in filtered if r['variant']==v]for v in('baseline','candidate')};med={v:statistics.median(a)for v,a in values.items()};pairs=[]
  for index in sorted({r['pair_index']for r in filtered}):
   pair={r['variant']:r for r in filtered if r['pair_index']==index};pairs.append((pair['candidate']['seconds']-pair['baseline']['seconds'])*1000)
  groups.append({'phase':phase,'flow':flow,'milliseconds':values,'median_ms':med,'paired_differences_ms':pairs,'median_paired_difference_ms':statistics.median(pairs),'median_change_percent':100*(med['candidate']/med['baseline']-1),'scope':'Small alternating-order observations, not a stable distribution. Unique input bytes differ per CLI.'})
 columns=('index','variant','flow','phase','pair_index','profile','cli_sha256','app_main_sha256','module_sha256','config_sha256','seconds','exit_code','correct','stdout_sha256','file_visible_seconds','output_already_current','file_visibility_right_censored_at_exit','file_polls','process_tree_user_seconds','process_tree_system_seconds','engine_cpu_seconds','engine_written_bytes','engine_io_delta','host_psi_delta_us','counter_bracket_seconds')
 save(out/'runtime-numeric.json',{'groups':groups,'commands':[{k:r[k]for k in columns}for r in rows],'summary':{k:v for k,v in summary.items()if k!='ordinary_lock_hashes'},'restoration':restored,'excluded_from_ordinary':['native correctness smoke','all explicit primers','profiles'],'setup_caveat':'First baseline greetings primer20.624s on newly copied source path; candidate does not independently repay that setup. Not a cold comparison.'})
 profiles={};execs={}
 for variant,index in [('baseline',35),('candidate',37)]:
  profiles[variant],execs[variant]=profile_details(next((P/'results-v1').glob(f'{index:02d}-*/run.wcprof.private')))
 save(out/'profile-numeric.json',{'profiles':profiles,'all_call_exec_class_count_maps_equal':execs['baseline']==execs['candidate'],'source_reducer_path':str(BASE),'source_reducer_sha256':sha(BASE),'scope':'One separately profiled, exactly primed check listing per CLI. No artifact-list profile in this trial. Inclusive sums overlap; unions are per class, not additive.'})
 print(json.dumps({'groups':groups,'profile_parity':execs['baseline']==execs['candidate'],'main_queries':{v:p['projection_boundary']['main_client_queries']for v,p in profiles.items()}},indent=2))
if __name__=='__main__':main()
