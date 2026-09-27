"""Numeric-only projection of four local cold/warm commands; raw output excluded."""
from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parent;raw=P/'results-v1';out=P/'evidence';out.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
rows=json.loads((raw/'results.json').read_text());clean=json.loads((raw/'cleanup.json').read_text());prov=json.loads((raw/'provenance.json').read_text());assert len(rows)==4 and all(r['correct']and r['exit_code']==0 and r['stdout_rows']==14 and not r['unexpected_cloud_link']for r in rows)
assert clean['attempts']==4 and clean['valid_commands']==4 and clean['cloud_commands']==0 and clean['fixture_unchanged'] and all(v['container_removed']and v['volume_removed']for v in clean['created_resources'])
projected=[]
for r in rows:
 devices={}
 for n,d in r['host_diskstats_delta'].items():
  if d[0]+d[4]:devices[n]={'reads':d[0],'writes':d[4],'read_mib':d[2]*512/2**20,'write_mib':d[6]*512/2**20,'mean_read_await_ms':d[3]/d[0]if d[0]else None,'mean_write_await_ms':d[7]/d[4]if d[4]else None,'busy_seconds':d[9]/1000}
 projected.append({k:r[k]for k in ('variant','phase','seconds','engine_start_to_ready_seconds_excluded','started_unix_ns','exited_unix_ns','exit_code','guard_abort','correct','stdout_sha256','stdout_rows','process_tree_user_seconds','process_tree_system_seconds','engine_io','engine_cpu','host_psi_us','host_dirty_writeback_start_kib','host_dirty_writeback_end_kib','free_disk_start','free_disk_end')}|{'engine_read_mib':r['engine_io']['rbytes']/2**20,'engine_write_mib':r['engine_io']['wbytes']/2**20,'host_devices':devices})
write('results.json',projected);write('cleanup.json',clean)
write('provenance.json',{k:prov[k]for k in ('image','sdk_manifest','build_manifest','build_manifest_sha256','build_recipe_sha256','source_sha256','expected_stdout_sha256','cloud_commands','command_cap','cache_boundary','order','timing','bounds','cleanup')}|{'fixture_manifest_sha256':sha(raw/'provenance.json'),'fixture_current_hashes_unchanged':True,'source_result_sha256':sha(raw/'results.json'),'fixture_source_and_raw_output_archived':False,'production_relation':'Linux v1 runtime binaries remain frozen. The committed v2 production correction only adds protocol-root slash acceptance on Windows; v3 is a test-oracle correction.'})
write('verification.json',{'commands':4,'exact_14_rows':True,'all_exit_zero':True,'no_guard_abort':True,'cloud_commands':0,'new_resources_removed':2,'existing_engines_modified':0,'fixture_unchanged':True,'one_fixed_order_pair_only':True,'source_results_sha256':sha(raw/'results.json'),'source_cleanup_sha256':sha(raw/'cleanup.json')})
report='''# Fresh-volume follow-up: explicit ancestor metadata

All four commands returned the exact same14-row `dagger check -l --all` listing. Both newly created containers and volumes were removed; the fixture was unchanged. No Cloud telemetry was enabled.

| Variant | First call on a new volume | Immediate warm repeat | Engine start to ready, excluded |
| --- | ---: | ---: | ---: |
| Baseline | 24.938 s | 1.623 s | 0.264 s |
| Explicit ancestor metadata | 24.568 s | 1.516 s | 0.245 s |

This single baseline-first pair does not demonstrate a general cold-start improvement. The roughly0.37 s difference is small relative to the approximately25 s first-call workload, and the order can benefit the candidate through host pages or remote services. The engine image, SDK blobs and generated source fixture were retained; each engine used a newly created Dagger volume and its first Dagger command was the listing. CLI time includes full process exit but excludes engine provisioning/startup. There was no hidden Dagger primer before either first call, no explicit image build/pull during setup, no host page-cache flush and no distributed-cache configuration.

The engine used87.82 CPU-seconds during baseline cold and87.97 during candidate cold. The ancestor change therefore does not remove the bulk of this cold workload. These are cumulative engine-cgroup counters, not wall time or an attribution to a specific compiler/process.

| CLI interval | Engine reads | Engine writes | Host Dirty at entry→exit | Host I/O full-pressure delta |
| --- | ---: | ---: | ---: | ---: |
| Baseline cold | 269.6 MiB | 668.1 MiB | 6.4→919.3 MiB | 145.3 ms |
| Baseline warm | 0.1 MiB | 535.1 MiB | 920.1→390.8 MiB | 24.2 ms |
| Candidate cold | 161.1 MiB | 1286.3 MiB | 5.5→300.1 MiB | 194.0 ms |
| Candidate warm | 0.3 MiB | 0 MiB | 300.5→307.1 MiB | 2.5 ms |

The write counters have an important boundary effect: the baseline's immediate warm interval contains535 MiB of engine-attributed writes while host Dirty falls sharply, whereas the candidate records its writes largely before cold exit. This is consistent with deferred writeback from the preceding cold work. It does not prove the precise producing call of every byte, and it would be wrong to call all535 MiB warm-listing write amplification. Both warm times can also include different amounts of outstanding cold I/O; their107.6 ms difference is not a clean isolated saving from the ancestor change.

The NVMe device's mean write await was about3.10 ms in baseline cold,5.06 ms in its warm repeat, and2.00 ms in candidate cold. These are whole-host device counters and include unrelated work. There was no large host I/O-pressure stall comparable to the previously observed multi-second disk contention in this pair. The4-call result helps explain why interval counters and disk state must be retained; it cannot resolve the historical27-versus45-second variability on its own.

The run enforced a16 GiB free-space floor, a sampled8 GiB cumulative engine-write guard and a300 s command timeout. No guard fired. It recorded about2.43 GiB of engine writes before final stop samples. The guard is not a storage quota; stop-time writeback can follow the last sample. Raw stdout/stderr, fixture source and resource identifiers remain private. The shareable projection contains only fixed variant labels, binary/source/image pins, exact-output hashes, timing/counter summaries and cleanup assertions.
'''
for a,b in [('same14','same 14'),('roughly0.37','roughly 0.37'),('approximately25','approximately 25'),('used87.82','used 87.82'),('and87.97','and 87.97'),('contains535','contains 535'),('all535','all 535'),('their107.6','their 107.6'),('about3.10','about 3.10'),(',5.06',', 5.06'),('and2.00','and 2.00'),('The4-call','The 4-call'),('historical27-versus45-second','historical 27-versus-45-second'),('a16 GiB','a 16 GiB'),('sampled8 GiB','sampled 8 GiB'),('a300 s','a 300 s'),('about2.43','about 2.43')]:report=report.replace(a,b)
(out/'report.md').write_text(report)
files=[out/'report.md',out/'results.json',out/'cleanup.json',out/'provenance.json',out/'verification.json',P/'runtime.py',P/'analyze.py',P/'README.md']
write('archive-allowlist.json',{'root':'/tmp/collections-perf','files':[{'path':str(p.relative_to('/tmp/collections-perf')),'sha256':sha(p)}for p in files],'exclude':['raw stdout/stderr','fixture files','Docker IDs and volume names','credentials','binaries']})
print(json.dumps({'verified_commands':4,'cloud_commands':0,'removed_created_resources':2,'evidence':str(out)}))
