from pathlib import Path
import collections,hashlib,json,statistics
HERE=Path(__file__).resolve().parent;SRC=HERE.parent/'cloud-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=json.loads((SRC/'results.json').read_text());rest=json.loads((SRC/'restoration.json').read_text())
groups=collections.defaultdict(list)
for r in rows:groups[(r['phase'],r['flow'],r['variant'])].append(r)
samples=[{k:r[k] for k in ('phase','flow','variant','index','production','seconds','correct','exit_code','timed_out','engine_cpu_seconds','engine_written_bytes','stdout_sha256','input_sha256')} for r in rows]
comparisons=[]
for phase,flow,n in [('local-warm','core',3),('local-warm','module',3),('local-fresh-input','module',1),('cloud-warm','core',3),('cloud-warm','module',3)]:
 a=groups[(phase,flow,'baseline')];b=groups[(phase,flow,'candidate')];assert len(a)==len(b)==n and all(r['correct'] for r in a+b)
 av=statistics.median(r['seconds'] for r in a);bv=statistics.median(r['seconds'] for r in b)
 pairs=[]
 for index in sorted({r['index']for r in a}):
  ar=next(r for r in a if r['index']==index);br=next(r for r in b if r['index']==index)
  pairs.append({'index':index,'baseline_seconds':ar['seconds'],'candidate_seconds':br['seconds'],'saved_ms':(ar['seconds']-br['seconds'])*1000})
 comparisons.append({'phase':phase,'flow':flow,'pairs':n,'baseline_median_ms':av*1000,'candidate_median_ms':bv*1000,'median_difference_ms':(av-bv)*1000,'median_reduction_percent':100*(av-bv)/av,'paired_values':pairs,'baseline_engine_cpu_median_ms':statistics.median(r['engine_cpu_seconds']for r in a)*1000,'candidate_engine_cpu_median_ms':statistics.median(r['engine_cpu_seconds']for r in b)*1000})
summary={'status':'32 benchmark/primer commands correct; appended collection correctness stopped after the first baseline CLI failure; candidate collection query not attempted','comparisons':comparisons,'restoration':rest,'ordinary_profiles':0,'cloud_attempts':14,'local_attempts':19,'raw_results_sha256':sha(SRC/'results.json'),'executed_driver_sha256':sha(SRC/'driver.py.txt'),'limits':['One common engine and retained volume, alternating CLI query paths; no cold-engine comparison.','Three warm pairs per flow; Cloud variability limits precision.','Local-only and normal Cloud sessions have different telemetry work and cannot substitute for each other.','The fresh-input test is one local pair on a native Dang fixture; baseline ran first and candidate reused the same engine after that edit. It validates output invalidation, not an independent first-run or SDK rebuild comparison.','Explicit primers are excluded from medians.','Collection parser correctness is incomplete; an unchanged baseline witness is required before classifying the failure.','Resource counters surround CLI timing and may include background work.']}
(HERE/'numeric-summary.json').write_text(json.dumps(summary,indent=2)+'\n');(HERE/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
lines=['# Bulk CLI metadata: ordinary command measurements','','One engine served both matched CLIs; only the metadata query path differed. All32 benchmark and primer commands returned expected output. No profiler or diagnostic hooks were enabled.','','| Flow | Old query | JSON snapshot | Repetitions |','| --- | ---: | ---: | ---: |']
for r in comparisons:
 label={'local-warm':'Local warm','cloud-warm':'Cloud warm','local-fresh-input':'Local fresh input'}[r['phase']]+' '+r['flow']
 lines.append(f"| {label} | {r['baseline_median_ms']:.1f} ms | {r['candidate_median_ms']:.1f} ms | {r['pairs']} pairs |")
lines+=['','Local warm medians improved by150.5ms for the core call and138.9ms for the native module call. Normal Cloud runs improved by36.6ms and6.1ms respectively in this small sample. The local improvement does not establish an equivalent Cloud improvement. Both modes still need separate end-to-end evaluation. The single edited-input pair ran baseline first on a shared engine; treat it as an invalidation check, not an independent first-run timing comparison.','','The added collection parser probe then failed on the old-query CLI with a missing `[GoModule]` TypeDef. The candidate probe was not run because the driver stops on failure. This is a correctness gate, not a timing sample; classification against the unchanged engine is pending.','','The driver restored input files and the original engine binary, stopped its owned engine, retained its volume and deleted no resources. It attempted14 Cloud and19 local commands. Raw outputs, telemetry profiles and engine binaries are excluded from this bundle.','','This is a response representation optimization. It preserves authoritative schema/view metadata and reduces thousands of getter results; it does not remove initial SDK or core TypeDef construction. The broader500ms target is not achieved for all flows.']
(HERE/'report.md').write_text('\n'.join(lines)+'\n')
files=[HERE/'derive.py',HERE/'numeric-summary.json',HERE/'samples.json',HERE/'report.md']
(HERE/'allowlist.txt').write_text(''.join(str(p)+'\n'for p in files));(HERE/'checksums.json').write_text(json.dumps({p.name:sha(p)for p in files},indent=2)+'\n')
print(json.dumps(comparisons,indent=2))
