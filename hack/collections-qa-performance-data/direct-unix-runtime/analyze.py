"""Produce an explicit safe numeric/source allowlist after the reviewed local run."""
from pathlib import Path
from collections import Counter
import hashlib,json,statistics
H=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def union(intervals):
 merged=[]
 for a,b in sorted(intervals):
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 return sum(b-a for a,b in merged)/1e6

def main():
 run=H/'results-v1';rows=json.loads((run/'results.json').read_text());rest=json.loads((run/'restoration.json').read_text())
 assert len(rows)==56 and all(r['correct']for r in rows)
 assert all(rest[k]for k in('fixtures_restored','original_engine_binary_untouched','original_engine_stopped','retained_volume_preserved','temporary_container_removed','private_socket_directory_removed'))
 out=H/'results-v1-evidence';assert not out.exists();out.mkdir()
 def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
 write('samples.json',rows);write('restoration.json',rest)
 ordinary={}
 for flow in('core','ws','call','check','generate','artifacts'):
  entry={}
  for variant in('docker','unix'):
   matched=[r for r in rows if r['phase']=='warm'and r['flow']==flow and r['variant']==variant];assert len(matched)==3
   entry[variant]={'seconds':[r['seconds']for r in matched],'median_seconds':statistics.median(r['seconds']for r in matched),'process_tree_cpu_seconds':[r['process_tree_user_seconds']+r['process_tree_system_seconds']for r in matched],'engine_cpu_seconds':[r['engine_cpu_seconds']for r in matched]}
  entry['paired_delta_ms']=[1000*(b-a)for a,b in zip(entry['docker']['seconds'],entry['unix']['seconds'])]
  entry['median_delta_ms']=1000*(entry['unix']['median_seconds']-entry['docker']['median_seconds'])
  entry['percent_change']=100*(entry['unix']['median_seconds']/entry['docker']['median_seconds']-1)
  ordinary[flow]=entry
 write('ordinary-summary.json',ordinary)
 profiles={}
 for i,row in enumerate(rows):
  if not row['profile']:continue
  path=run/f"{i:02d}-{row['block']}-{row['phase']}-{row['flow']}-{row['variant']}"/'run.wcprof.private'
  with path.open()as f:header=json.loads(next(f));ops=[json.loads(line)for line in f if line.strip()]
  ops=[op for op in ops if op.get('e')=='op'];strings=header['strings'];origin=min(op['s']for op in ops)
  name=lambda op:strings[op.get('c',0)]
  def facts(selected):return {'count':len(selected),'inclusive_sum_ms':sum(o['d']-o['s']for o in selected)/1e6,'interval_union_ms':union([(o['s'],o['d'])for o in selected]),'intervals':[{'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}for o in sorted(selected,key=lambda o:o['s'])]}
  labels={'session_queries':('session_phase','session.query'),'catalog':('call_exec','Workspace.artifacts'),'expansion':('call_exec','Artifacts.__itemsJSON'),'git_advertisements':('internal','git.publicAdvertisement'),'parent_sync':('io','filesync.syncParentDirs'),'host_directory':('call_exec','Host.directory')}
  p={'profile_sha256':sha(path),'instrumented_cli_seconds':row['seconds'],'op_count':len(ops),'kinds':dict(Counter(o['k']for o in ops)),'dropped_events':header['dropped_events'],'open_operations':len(header.get('open_ops',[])),'operation_window_ms':(max(o['d']for o in ops)-origin)/1e6,'phases':{label:facts([o for o in ops if o['k']==kind and name(o)==cl])for label,(kind,cl)in labels.items()},'limits':'Fully primed separate check-l profile; not an ordinary latency sample. Inclusive and interval-union values are not independent/additive critical-path savings. No Cloud exporter in either arm.'}
  assert not p['dropped_events']and not p['open_operations'];profiles[row['variant']]=p
 write('profiles.json',profiles)
 p=json.loads((run/'provenance.json').read_text());write('provenance.json',{'cli_sha256':p['cli']['sha256'],'engine_sha256':p['engine_manifest']['engine']['sha256'],'engine_manifest_sha256':p['engine_manifest_sha256'],'frozen_inputs_sha256':p['frozen_inputs_sha256'],'source_head':p['engine_manifest']['source_head'],'expected_core_version':p['expected_core_version'],'driver_sha256':sha(run/'driver.py.txt'),'numeric_results_sha256':sha(run/'results.json'),'cloud_commands':0,'call_count':56,'ordinary_count':36,'primers':12,'sentinel_calls':4,'separate_profile_primers':2,'separate_profiles':2,'cache_boundary':p['cache_boundary'],'scope':p['scope'],'image_loader_both':p['image_loader_both'],'socket_checks':json.loads((run/'starts.json').read_text()),'fixture_sha256':p['fixtures_before']})
 lines=['The56-command local-only comparison completed with all expected outcomes. It used the same original CLI and the same engine process/retained volume; the only selector change was Docker exec versus an existing direct Unix endpoint. Both arms retained Docker image attachables. Private socket permissions and original-container/volume exclusivity were checked; the new container/socket directory were removed and original fixtures/container/binary preserved.','','There are three ordinary paired samples per flow, with alternating order rotated across flows. They are exploratory measurements on one Linux host, not stable distributions. Twelve exact primers, four fail/restore sentinel calls and four separate profile-phase calls are excluded from ordinary medians.','','| Flow | Docker samples (ms) | Unix samples (ms) | Median change (ms) |','| --- | --- | --- | ---: |']
 for flow,p in ordinary.items():lines.append(f"| {flow} | {' / '.join(f'{s*1000:.1f}'for s in p['docker']['seconds'])} | {' / '.join(f'{s*1000:.1f}'for s in p['unix']['seconds'])} | {p['median_delta_ms']:+.1f} |")
 lines+=['','Native check is the standard fixture check and its failure sentinel is verified independently on both transports. Warm native generation already has current output; it is not SDK code generation or a fresh edit. Expanded artifacts and the separately profiled14-row check listing retain their output oracles.','','This demonstrates the existing local Unix capability only. No automatic production fast path, remote Docker/Desktop support, fresh-volume cold, service-up or Cloud result is measured. CPU values count CLI children and engine cgroup work separately; they must not be summed into a predicted wall saving. The existing fixture sits under a wide /tmp, identically for both arms.','','The profiles follow full identical check-list primers and are excluded from ordinary medians. Git HTTP attribution is a separate diagnostic analysis; inclusive spans overlap.']
 lines+=['','Raw Unix also bypasses the container driver Available→docker version admission probe. Measured differences combine driver admission and replacing Docker exec tunnels, not tunnel-only savings. The Docker image loader override does not restore the skipped admission probe.']
 (out/'report.md').write_text('\n'.join(lines)+'\n')
 for n in('runtime.py','analyze.py','source-review.md'):(out/n).write_bytes((H/n).read_bytes())
 write('archive-allowlist.json',{'files':['samples.json','restoration.json','ordinary-summary.json','profiles.json','provenance.json','report.md','runtime.py','analyze.py','source-review.md'],'exclude':'Raw stdout/stderr, profiles, engine/container IDs, socket endpoint and credentials/config.'})
 print(json.dumps({'evidence':str(out),'flows':{f:{'docker_ms':p['docker']['median_seconds']*1000,'unix_ms':p['unix']['median_seconds']*1000,'delta_ms':p['median_delta_ms']}for f,p in ordinary.items()}}))
if __name__=='__main__':main()
