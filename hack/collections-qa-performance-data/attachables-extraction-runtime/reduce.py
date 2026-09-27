from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;R=H/'smoke/results-v1';E=H/'evidence';E.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=json.loads((R/'results.json').read_text());rest=json.loads((R/'restoration.json').read_text());policy=json.loads((R/'dispatch-policy.json').read_text());prov=json.loads((R/'provenance.json').read_text())
assert len(rows)==10 and all(r['correct']and r['exit_code']==0 and not r['profile']and not r['unexpected_cloud_link']for r in rows)
assert rest['validated_commands']==10 and rest['local_attempts']==10 and all(rest[k]for k in ['fixtures_restored','original_engine_binary_untouched','original_init_binary_untouched','original_engine_stopped','retained_volume_preserved','temporary_container_removed'])
assert rest['cleanup_error_type']is None and rest['cloud_commands']==0
fields=['variant','flow','phase','block','profile','expected_failure','input_sha256','app_main_sha256','app_test_sha256','seconds','exit_code','timed_out','correct','stdout_sha256','unexpected_cloud_link']
summary={'scope':'Ten local correctness/setup calls only. Durations are retained as raw provenance, not paired performance samples or cold/warm comparisons. No profiles or measured process counts.','source_driver_sha256':sha(H/'runtime.py'),'raw_results_sha256':sha(R/'results.json'),'raw_provenance_sha256':sha(R/'provenance.json'),'engine_sha256':'ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1','cli_sha256':prov['cli']['sha256'],'helper_variants':{k:{n:v[n]for n in ['sha256','bytes']}for k,v in prov['helper_variants'].items()},'outcomes':[{f:r[f]for f in fields}for r in rows],'restoration':rest,'dispatch_policy':policy,'limits':{'all_validation_on_linux_amd64':True,'existing_unix_socket_test_needs_platform_guard_for_portable_upstream_suite':True,'reflective_concrete_type_package_path_changes':True},'cross_language_correctness':{v:{r['flow']:r['correct']for r in rows if r['variant']==v}for v in ['baseline','candidate']}}
(E/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
report='''# Extracted attachables helper: real SDK correctness

**All 10 local checks passed:** Go module source read, TypeScript runtime build/read, Python constructor/default-factory read, a selected Go check with a unique test-body edit, and an ordinary container exec, once per helper binary.

Both arms used the same ordinary ec6 engine and original d685 CLI. Only the heavy init binary changed; no light PID1 or separate helper mount was used. The container exec verified the mounted `/.init` hash for its arm and absence of `/.dagger-session`. Go, TypeScript and Python fixture configurations explicitly disable default function caching; selected Go test bodies and ordinary exec arguments were unique. No profiler or process-count measurement was used.

The driver validated exact source/file contents and the selected check's successful result, then verified complete restoration: original engine/init unchanged and stopped, all fixtures restored, temporary container removed, retained volume preserved. It made zero Cloud calls and deleted zero volumes. Engine writes bracketing the ten commands totaled 1,273,856 bytes.

These are correctness/setup calls, including SDK preparation and fresh Go compilation. Their raw durations are retained in summary.json, but are not a performance comparison. The independent warm-host helper startup measurement remains 9.114→6.357 ms median over twelve alternating pairs; it does not establish a whole-CLI improvement.

Validation covers Linux/amd64. Moved production bodies keep existing platform behavior; the new Unix socket test needs a platform constraint for a portable upstream suite. Exported aliases preserve ordinary source API use, while reflected defining package paths change. No production source was edited by this driver.
'''
(E/'report.md').write_text(report)
files=['summary.json','report.md']
for n in ['runtime.py','prepare.py','reduce.py','runtime-vs-reviewed.diff','frozen-runtime-manifest.json','frozen-inputs.json','fixture-inventory.json']:
 (E/n).write_bytes((H/n).read_bytes());files.append(n)
(E/'checksums.json').write_text(json.dumps({n:sha(E/n)for n in files},indent=2)+'\n');files+=['checksums.json','allowlist.txt'];(E/'allowlist.txt').write_text('\n'.join(files)+'\n')
print(json.dumps({'safe_files':len(files),'validated':10,'restored':True,'cloud_calls':0,'summary_sha256':sha(E/'summary.json')}))
