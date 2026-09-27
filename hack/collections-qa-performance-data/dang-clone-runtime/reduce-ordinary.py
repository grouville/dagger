#!/usr/bin/env python3
"""Reduce the frozen local36 trial to allowlisted numeric evidence only."""
import hashlib,json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
OUT=HERE/'safe-evidence-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=json.loads((HERE/'results-numeric.json').read_text())
assert len(rows)==36 and all(r['correct']and not r['timed_out']and not r['unexpected_cloud_link']for r in rows)
keep=('global_index','variant','flow','phase','block','profile','seconds','file_visible_seconds','file_visibility_poll_interval_ms','output_already_current','exit_code','correct','process_tree_user_seconds','process_tree_system_seconds','engine_cpu_seconds','engine_written_bytes','host_psi_delta_us','counter_bracket_seconds','stdout_sha256','app_main_sha256','app_test_sha256','native_input_sha256')
safe=[{k:r[k]for k in keep}for r in rows]
groups=[]
for phase,flow in [('warm','checks'),('warm','artifacts'),('fresh-comment','checks'),('fresh-input','generate')]:
 g={'phase':phase,'flow':flow,'interpretation':'ABBA exploratory observations, not independent randomized pairs'}
 for v in ('baseline','candidate'):
  rs=[r for r in rows if(r['variant'],r['phase'],r['flow'])==(v,phase,flow)]
  g[v]={'n':len(rs),'raw_ms':[r['seconds']*1000 for r in rs],'median_ms':statistics.median(r['seconds']*1000 for r in rs),'engine_cpu_ms':[r['engine_cpu_seconds']*1000 for r in rs],'cli_tree_cpu_ms':[(r['process_tree_user_seconds']+r['process_tree_system_seconds'])*1000 for r in rs],'file_visible_ms':[r['file_visible_seconds']*1000 if r['file_visible_seconds']is not None else None for r in rs]}
 diffs=[]
 for b,c in [(0,1),(3,2)]:
  br=next(r for r in rows if(r['block'],r['phase'],r['flow'])==(b,phase,flow));cr=next(r for r in rows if(r['block'],r['phase'],r['flow'])==(c,phase,flow))
  diffs.append({'baseline_block':b,'candidate_block':c,'candidate_minus_baseline_ms':(cr['seconds']-br['seconds'])*1000})
 g['aligned_block_differences']=diffs
 g['median_change_ms']=g['candidate']['median_ms']-g['baseline']['median_ms'];groups.append(g)
rest=[]
for f in sorted(HERE.glob('block-*/lifecycle-restoration.json')):
 v=json.loads(f.read_text());assert all(v[k]for k in ('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))and not v['cleanup_error_types'];rest.append({'block':int(f.parent.name.split('-')[1]),**v})
assert len(rest)==6
summary=json.loads((HERE/'summary-v1.json').read_text());assert summary['validated_commands']==36 and all(summary['fixtures_restored'].values())and summary['original_public_fixture_untouched']
manifest=json.loads(Path('/tmp/collections-perf/dang-clone-inplace-v1/engine-builds-v2/runtime-builds.json').read_text())
provenance={'driver_sha256':sha(HERE/'runtime.py'),'lifecycle_sha256':sha(HERE/'lifecycle.py'),'frozen_inputs_sha256':sha(HERE/'frozen-runtime-inputs.json'),'build_manifest_sha256':sha('/tmp/collections-perf/dang-clone-inplace-v1/engine-builds-v2/runtime-builds.json'),'build_recipe_sha256':manifest['recipe_sha256'],'source_head':manifest['source_head'],'cli_sha256':manifest['cli']['sha256'],'variants':{k:{'engine_sha256':v['engine']['sha256'],'effective_parent_engine_sha256':v['effective_parent_engine_sha256'],'manifest_sha256':v['manifest_sha256'],'expected_core_version':v['expected_core_version']}for k,v in manifest['variants'].items()},'go_module_sha256':'0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'}
result={'status':'complete','local_commands':36,'cloud_commands':0,'rows':safe,'groups':groups,'restoration':rest,'fixtures_restored':summary['fixtures_restored'],'original_public_fixture_untouched':summary['original_public_fixture_untouched'],'measured_command_engine_write_bytes':summary['measured_command_engine_write_bytes'],'write_scope':summary['write_scope'],'first_selected_control':{'wall_seconds':rows[4]['seconds'],'reported_selected_check_seconds':43.2,'dispatch_outcome':'exactly one selected Go unit test passed','internal_compile_download_process_attribution':'unavailable in retained default-progress stderr; no profile captured for this command','comparability':'first execution on retained engine state; not a clone A/B sample'},'provenance':provenance}
OUT.mkdir(exist_ok=True);(OUT/'numeric.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'local_commands':36,'correct':36,'restoration_blocks':len(rest),'output':str(OUT/'numeric.json')}))
