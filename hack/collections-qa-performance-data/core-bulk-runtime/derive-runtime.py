"""Offline numeric reduction of the local core metadata ABBA run; no raw payloads."""
from pathlib import Path
from collections import Counter
import hashlib, json, statistics
HERE=Path(__file__).resolve().parent
RUN=HERE/'runtime-v2'; OUT=HERE/'runtime-evidence-v2'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def union(xs):
    intervals=[]
    for a,b in sorted((x['s'],x['d']) for x in xs):
        if intervals and a<=intervals[-1][1]:intervals[-1][1]=max(b,intervals[-1][1])
        else:intervals.append([a,b])
    return sum(b-a for a,b in intervals)/1e6
rows=json.loads((RUN/'results.json').read_text()); restoration=json.loads((RUN/'restoration.json').read_text())
assert len(rows)==38 and all(r['correct'] for r in rows)
assert restoration['cloud_commands']==0 and restoration['engine_stopped'] and restoration['original_binary_restored'] and restoration['fixtures_unchanged']
OUT.mkdir(exist_ok=False)
summary=[]
for phase in ('first-api-after-restart','explicit-primer','warm'):
    for flow in ('core','module','listing'):
        selected=[r for r in rows if r['phase']==phase and r['flow']==flow]
        if not selected:continue
        entry={'phase':phase,'flow':flow,'variants':{}}
        for variant in ('baseline','candidate'):
            xs=[r for r in selected if r['variant']==variant]
            entry['variants'][variant]={'n':len(xs),'samples_ms':[r['seconds']*1000 for r in xs],
                'median_ms':statistics.median(r['seconds']*1000 for r in xs),
                'median_engine_cpu_ms':statistics.median(r['engine_cpu_seconds']*1000 for r in xs),
                'engine_write_bytes_total':sum(r['engine_written_bytes'] for r in xs)}
        b=entry['variants']['baseline']['median_ms'];c=entry['variants']['candidate']['median_ms']
        entry.update(delta_ms=c-b,percent=(c/b-1)*100)
        summary.append(entry)
profiles=[]
allowed={
 'call':['Query.__currentTypeDefsJSON','Query.currentTypeDefs','ObjectTypeDef.__withFunction','ObjectTypeDef.__withFunctions','InterfaceTypeDef.__withFunction','InterfaceTypeDef.__withFunctions','Function.__withArg','Query.__function','Query.__functionArgExact','Function.withDescription'],
 'call_exec':['Query.__currentTypeDefsJSON','Query.currentTypeDefs','ObjectTypeDef.__withFunction','ObjectTypeDef.__withFunctions','InterfaceTypeDef.__withFunction','InterfaceTypeDef.__withFunctions'],
 'internal':['dagql.publishResult'],
 'session_phase':['session.query','session.schemaBuild'],
}
for variant in ('baseline','candidate'):
    paths=list(RUN.glob('*-diagnostic-first-api-after-restart-*-core-'+variant+'/run.wcprof'))
    assert len(paths)==1
    p=paths[0]
    with p.open()as f:
        h=json.loads(next(f));ops=[json.loads(line)for line in f if line.strip()]
    ops=[x for x in ops if x.get('e')=='op'];names=h['strings']
    assert h['dropped_events']==0 and not h.get('open_ops')
    phases=[]
    for kind,classes in allowed.items():
        for name in classes:
            xs=[x for x in ops if x['k']==kind and names[x.get('c',0)]==name]
            phases.append({'kind':kind,'class':name,'count':len(xs),'inclusive_sum_ms':sum(x['d']-x['s']for x in xs)/1e6,
                'interval_union_ms':union(xs),'max_ms':max((x['d']-x['s']for x in xs),default=0)/1e6,
                'outcomes':dict(Counter(x.get('o','')for x in xs))})
    profiles.append({'variant':variant,'profile_sha256':sha(p),'operation_count':len(ops),'dropped_events':0,'open_ops':0,
        'profile_window_ms':(max(x['d']for x in ops)-min(x['s']for x in ops))/1e6,'phases':phases})
write(OUT/'summary.json',{'ordinary':summary,'cloud_commands':0,'validated_commands':38,'profiles':profiles,
    'limits':['Retained same volume and warm host pages/images; first API after process restart is not cold-volume startup.',
    'Two first-API samples and four warm samples per variant; report all raw values, not a general promise.',
    'Separate profiles are diagnostics, excluded from ordinary medians; inclusive and union times overlap.',
    'Engine CPU/I/O counters bracket the CLI and include any background activity.']})
write(OUT/'samples.json',rows)
write(OUT/'provenance.json',{'runtime_driver_sha256':sha(RUN/'driver.py.txt'),'reducer_sha256':sha(__file__),
    'runtime_results_sha256':sha(RUN/'results.json'),'build_manifest':json.loads((HERE/'builds/runtime-builds.json').read_text()),
    'restoration':restoration,'starts':json.loads((RUN/'starts.json').read_text()),
    'rejected_v1':{'reason':'Stale version expectation from HEAD21939 instead of exact frozen HEAD85; command exit0, golden mismatch. No behavior failure.',
      'local_commands':1,'results_sha256':sha(HERE/'runtime-v1/results.json'),'restoration':json.loads((HERE/'runtime-v1/restoration.json').read_text())}})
lines=['The four process-restart blocks ran baseline / candidate / candidate / baseline on the same retained owned Dagger volume. All38 local commands passed their exact stdout and fixture checks; the original engine binary was restored and stopped. No Cloud calls ran.',
'', '| Flow | Baseline median | Candidate median | Difference | Samples per variant |','| --- | ---: | ---: | ---: | ---: |']
for e in summary:
    if e['phase']=='explicit-primer':continue
    b=e['variants']['baseline'];c=e['variants']['candidate']
    lines.append(f"| {e['phase']}: {e['flow']} | {b['median_ms']:.1f} ms | {c['median_ms']:.1f} ms | {e['delta_ms']:+.1f} ms ({e['percent']:+.1f}%) | {b['n']} |")
lines+=['','Engine process startup/stop, priming and profile downloads are excluded from ordinary timings. First API means the first command after an engine-process restart on the existing volume; persisted results can be reused. The two separate profiled commands identify construction/cache work and are not latency samples. CPU/I/O counters include any engine background work.',
'','The preceding harness attempt is retained separately: its first command succeeded but returned the new frozen build version, while the harness still expected the old build version. It made one local command and restored the engine; it is excluded from this comparison.',
'','These results validate the runtime behavior of the bulk consumer on this experimental SDK stack. They must be read alongside the three-pair fresh library construction benchmark; neither establishes a general improvement across all workflows. Raw numeric samples and phase counts are in the accompanying JSON.']
(OUT/'report.md').write_text('\n'.join(lines)+'\n')
(OUT/'derive-runtime.py').write_bytes(Path(__file__).read_bytes())
files=['report.md','summary.json','samples.json','provenance.json','derive-runtime.py']
write(OUT/'checksums.json',{name:sha(OUT/name)for name in files});files.append('checksums.json')
(OUT/'allowlist.txt').write_text('\n'.join(files)+'\n')
print(json.dumps(summary,indent=2))
