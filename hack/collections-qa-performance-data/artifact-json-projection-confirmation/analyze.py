#!/usr/bin/env python3
"""Offline artifact confirmation reduction; no calls or raw-output publication."""
from pathlib import Path
import hashlib,json,statistics,shutil
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 rows=json.loads((P/'results-numeric.json').read_text());summary=json.loads((P/'summary-v1.json').read_text());restored=json.loads((P/'results-v1/lifecycle-restoration.json').read_text());assert len(rows)==16 and all(r['correct']for r in rows)and restored['validated_commands']==16 and not restored['cleanup_error_types']
 assert summary['prior_fixture_restored']and summary['original_fixture_untouched']and all(restored[k]for k in ('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))
 warm=[r for r in rows if r['phase']=='warm'];pairs=[]
 for index in range(6):
  chronological=[r for r in warm if r['pair_index']==index];pair={r['variant']:r for r in chronological};assert len(chronological)==2
  pairs.append({'pair_index':index,'order':[r['variant']for r in chronological],'baseline_ms':pair['baseline']['seconds']*1000,'candidate_ms':pair['candidate']['seconds']*1000,'candidate_minus_baseline_ms':(pair['candidate']['seconds']-pair['baseline']['seconds'])*1000,'second_minus_first_ms':(chronological[1]['seconds']-chronological[0]['seconds'])*1000,'engine_cpu_seconds_chronological':[r['engine_cpu_seconds']for r in chronological],'cli_process_tree_cpu_seconds_chronological':[r['process_tree_user_seconds']+r['process_tree_system_seconds']for r in chronological],'engine_written_bytes_chronological':[r['engine_written_bytes']for r in chronological]})
 values={v:[r['seconds']*1000 for r in warm if r['variant']==v]for v in('baseline','candidate')}
 stats={v:{'values_ms':x,'median_ms':statistics.median(x),'mean_ms':statistics.mean(x),'min_ms':min(x),'max_ms':max(x),'sample_stddev_ms':statistics.stdev(x)}for v,x in values.items()}
 difference=[p['candidate_minus_baseline_ms']for p in pairs]
 columns=('index','variant','phase','pair_index','profile','cli_sha256','module_sha256','config_sha256','seconds','correct','exit_code','stdout_sha256','engine_cpu_seconds','engine_io_delta','engine_written_bytes','host_psi_delta_us','process_tree_user_seconds','process_tree_system_seconds','counter_bracket_seconds')
 out=P/'evidence-v1';assert not out.exists();out.mkdir()
 numeric={'local_commands':16,'cloud_commands':0,'scope':summary['scope'],'stats':stats,'paired_differences_ms':difference,'paired_median_ms':statistics.median(difference),'paired_mean_ms':statistics.mean(difference),'pairs':pairs,'candidate_faster_pairs':sum(d<0 for d in difference),'second_command_slower_pairs':sum(p['second_minus_first_ms']>0 for p in pairs),'order_group_median_delta_ms':{order:statistics.median(p['candidate_minus_baseline_ms']for p in pairs if p['order'][0]==order)for order in('baseline','candidate')},'commands':[{k:r[k]for k in columns}for r in rows],'summary':summary,'restoration':restored,'limitations':['Four explicit primers are excluded.','No profiles, source edits, cold start or production Cloud measured here.','Alternating pair order makes the first command follow the same CLI as the preceding command and the second switch CLIs; position and switch effects are not independently identifiable.','Aggregate counters do not identify network, GC or page-cache causes.']}
 save(out/'numeric.json',numeric)
 for name in ('runtime.py','lifecycle.py','freeze.py','analyze.py','lifecycle-vs-reviewed.patch','frozen-runtime-inputs.json','frozen-cli-manifest.json','frozen-engine-manifest.json','module-manifest.toml'):shutil.copyfile(P/name,out/name)
 print(json.dumps({'stats':stats,'paired_median_ms':numeric['paired_median_ms'],'paired_mean_ms':numeric['paired_mean_ms'],'second_slower_pairs':numeric['second_command_slower_pairs'],'all_correct':True},indent=2))
if __name__=='__main__':main()
