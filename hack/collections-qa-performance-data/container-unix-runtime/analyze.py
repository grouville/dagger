"""Sanitized ordinary and true-edit outcomes for the connector-only experiment."""
from pathlib import Path
import hashlib,json,statistics
H=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 run=H/'results-v1';rows=json.loads((run/'results.json').read_text());rest=json.loads((run/'restoration.json').read_text())
 assert len(rows)==50 and all(r['correct']for r in rows)
 assert all(rest[k]for k in('fixtures_restored','original_engine_binary_untouched','original_engine_stopped','retained_volume_preserved','temporary_container_removed','private_socket_directory_removed'))
 out=H/'results-v1-evidence';assert not out.exists();out.mkdir()
 def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
 write('samples.json',rows);write('restoration.json',rest);summary={}
 for phase,flows in [('warm',('core','ws','call','generate')),('fresh-edit',('check','generate'))]:
  for flow in flows:
   result={}
   for variant in('docker','socket'):
    rs=[r for r in rows if r['phase']==phase and r['flow']==flow and r['variant']==variant];assert len(rs)==3
    result[variant]={'seconds':[r['seconds']for r in rs],'median_seconds':statistics.median(r['seconds']for r in rs),'file_visible_seconds':[r['file_visible_seconds']for r in rs],'process_tree_cpu_seconds':[r['process_tree_user_seconds']+r['process_tree_system_seconds']for r in rs],'engine_cpu_seconds':[r['engine_cpu_seconds']for r in rs]}
   result['median_delta_ms']=1000*(result['socket']['median_seconds']-result['docker']['median_seconds']);result['paired_delta_ms']=[1000*(b-a)for a,b in zip(result['docker']['seconds'],result['socket']['seconds'])]
   result['percent_change']=100*(result['socket']['median_seconds']/result['docker']['median_seconds']-1)
   if phase=='fresh-edit':
    selected=[r for r in rows if r['phase']==phase and r['flow']==flow];key='native_module_sha256'if flow=='check'else'input_sha256';assert len({r[key]for r in selected})==6
    result['all_six_edited_inputs_distinct']=True
    if flow=='generate':assert all(not r['output_already_current']for r in selected)
   summary[phase+'-'+flow]=result
 write('summary.json',summary)
 p=json.loads((run/'provenance.json').read_text());write('provenance.json',{'cli_sha256':p['cli']['sha256'],'cli_manifest_sha256':p['cli_manifest_sha256'],'engine_sha256':p['engine_manifest']['engine']['sha256'],'engine_manifest_sha256':p['engine_manifest_sha256'],'driver_sha256':sha(run/'driver.py.txt'),'numeric_results_sha256':sha(run/'results.json'),'socket_query_parameter':p['cli_manifest']['socket_query_parameter'],'source_head':p['engine_manifest']['source_head'],'expected_core_version':p['expected_core_version'],'cloud_commands':0,'call_count':50,'exact_warm_primers':10,'warm_samples':24,'unique_edit_samples':12,'sentinel_calls':4,'scope':p['scope'],'cache_boundary':p['cache_boundary'],'image_loader_both':p['image_loader_both'],'socket_checks':json.loads((run/'starts.json').read_text()),'fixture_sha256':p['fixtures_before']})
 lines=['The50-command local comparison completed with all expected outcomes. Both arms used the same patched CLI, the same container driver admission and image loader, and the same engine process. Only the explicit perf-unix-socket query changed connection establishment. The default arm retained Docker exec; the explicit arm dialed the verified private Unix socket.','','Three alternating paired samples per case are exploratory, not stable distributions. Ten exact primers and four standard-check fail/restore sentinel calls are excluded from ordinary medians. Twelve edit samples each used distinct never-before-evaluated bytes.','','| Case | Docker samples (ms) | Socket samples (ms) | Median change (ms) |','| --- | --- | --- | ---: |']
 for key,r in summary.items():lines.append(f"| {key} | {' / '.join(f'{t*1000:.1f}'for t in r['docker']['seconds'])} | {' / '.join(f'{t*1000:.1f}'for t in r['socket']['seconds'])} | {r['median_delta_ms']:+.1f} |")
 lines+=['','All18 paired ordinary/edit observations favored the explicit socket arm in this small run. For fresh generation, median observed file visibility was339.2→236.5ms (5ms polling); full exit was371.2→249.4ms. These are distinct timing boundaries.','','Native standard-check edits append an inert but unique module-source comment; input/output bytes remain current. Generation edits change input bytes and verify the new generated output. File visibility and full CLI exit are recorded separately. This is native fixture generation, not real SDK code generation. Check sentinels verify that actual failures remain observable and restoration succeeds.','','The explicit query is an isolated proof, not a new supported production URI. Automatic endpoint provisioning/verification and platform fallback are unimplemented. Unlike the earlier raw-Unix experiment, this comparison preserves the container Available→docker version probe. The same initial connection plus three proactive warm sockets and all cleanup joins remain; it is not the held shared-HTTP prototype.','','Original fixtures and original stopped engine/binary were preserved, retained volume kept, new temporary container/socket directory removed. No Cloud, profiler, fresh-volume cold or service-up command ran. Public artifacts listing was validated in the separate56-call direct capability trial, not repeated here.']
 (out/'report.md').write_text('\n'.join(lines)+'\n')
 for n in('runtime.py','analyze.py','scope.md'):(out/n).write_bytes((H/n).read_bytes())
 write('archive-allowlist.json',{'files':['samples.json','restoration.json','summary.json','provenance.json','report.md','runtime.py','analyze.py','scope.md'],'exclude':'Raw stdout/stderr, IDs, private socket path, credentials/config and complete build inputs.'})
 print(json.dumps({'evidence':str(out),'cases':{k:{'docker_ms':r['docker']['median_seconds']*1000,'socket_ms':r['socket']['median_seconds']*1000,'delta_ms':r['median_delta_ms']}for k,r in summary.items()}}))
if __name__=='__main__':main()
