"""Reduce completed local trials to explicit numeric/source evidence only."""
from pathlib import Path
import argparse,hashlib,json,statistics,shutil
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).parent);a=p.parse_args();H=a.root;R=H/'results-v1';E=H/'results-v1-evidence';E.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,data): (E/name).write_text(json.dumps(data,indent=2)+'\n')
r=json.loads((R/'results.json').read_text());restore=json.loads((R/'restoration.json').read_text());assert all(x['correct']for x in r);assert all(restore[k]for k in ('fixtures_restored','original_engine_binary_untouched','original_engine_stopped','retained_volume_preserved','temporary_container_removed'));assert restore['cloud_commands']==0
keys=('variant','flow','phase','block','profile','expected_failure','input_sha256','app_main_sha256','native_module_sha256','seconds','exit_code','correct','stdout_sha256','timed_out','unexpected_cloud_link','file_visible_seconds','output_already_current','file_visible_censored_at_exit','file_poll_ms','file_polls','process_tree_user_seconds','process_tree_system_seconds','engine_cpu_seconds','engine_written_bytes','counter_bracket_seconds','host_psi_delta_us')
write('samples.json',[{'index':i,**{k:x[k]for k in keys if k in x}}for i,x in enumerate(r)])
summary={}
for phase in ('warm','fresh-edit','control','stopped-resume'):
 for flow in sorted({x['flow']for x in r if x['phase']==phase}):
  entry={}
  for v in ('baseline','candidate'):
   xs=[x for x in r if x['phase']==phase and x['flow']==flow and x['variant']==v and not x['profile']];values=[x['seconds']*1000 for x in xs];entry[v]={'n':len(xs),'milliseconds':values,'median_ms':statistics.median(values),'process_tree_cpu_ms':[1000*(x['process_tree_user_seconds']+x['process_tree_system_seconds'])for x in xs],'engine_cpu_ms':[1000*x['engine_cpu_seconds']if x.get('engine_cpu_seconds')is not None else None for x in xs]}
  entry['median_delta_ms']=entry['candidate']['median_ms']-entry['baseline']['median_ms'];entry['change_percent']=100*entry['median_delta_ms']/entry['baseline']['median_ms'];summary[phase+'/'+flow]=entry
write('summary.json',summary);write('restoration.json',restore)
prov=json.loads((R/'provenance.json').read_text());safe={k:prov[k]for k in ('driver_sha256','engine_manifest_sha256','frozen_inputs_sha256','commands_cap','cloud_commands','cache_boundary','timing','scope','limits','ambient_width_caveat')}
safe['cli']=prov.get('cli',prov.get('cli_manifest'));safe['fixture_hashes']=prov['fixtures_before'];safe['engine_build_manifest']=prov['engine_manifest'];safe['source_note']='The runtime CLI is explicitly pinned separately; an engine-build manifest CLI reference does not select the runtime CLI.';write('provenance.json',safe)
for name in ('runtime.py','frozen-engine-manifest.json','frozen-inputs.json','frozen-cli-manifest.json','independent-review.md'):
 if(H/name).exists():shutil.copyfile(H/name,E/name)
write('input-hashes.json',{str(p.relative_to(H)):sha(p)for p in [H/'runtime.py',R/'results.json',R/'restoration.json',R/'provenance.json',H/'frozen-engine-manifest.json',H/'frozen-inputs.json']})
print(json.dumps({key:{v:round(value[v]['median_ms'],2)for v in ('baseline','candidate')}for key,value in summary.items()},indent=2))
