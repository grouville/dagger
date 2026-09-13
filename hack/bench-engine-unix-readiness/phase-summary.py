#!/usr/bin/env python3
"""Readiness and image phases for same-CLI Unix socket helper engine pairs; not additive CPU."""
import json
from pathlib import Path
import statistics
import sys

OWNER = Path(__file__).resolve().parent
cohort = Path(sys.argv[1]).resolve(strict=True)
assert cohort.parent == Path('/tmp') and cohort.name.startswith('dagger-rust-unix-readiness-ab-')
report = json.loads((cohort/'analysis-r2/report.json').read_text())
assert report['all_captures_pass'] and report['cross_side_image_byte_sets_equal']
meta = report['metadata']
assert len(set(meta['image_ids'].values())) == 2
assert set(meta['cli_sha256'].values()) == {'6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad'}
largest = 'sha256:167b9fde7ea2106ff0349f834ad13f3d5078836087edf8a9422da759c088f66c'
fields = ('process_ms','cargo_ms','rust_delivery_envelope_ms','connect_ms','creating_client_ms','info_total_ms','info_first_ms','info_version_ms','info_gap_ms','dpkg_ms','rustup_ms')
samples = []
for r in report['profiles']:
    if r['label'] != 'warmup-dagger':
        continue
    point = {key:r[key] for key in ('index','side','process_ms','cargo_ms','rust_delivery_envelope_ms','replay_drift')}
    trace = cohort/'analysis-r2'/f'{r["index"]}-{r["side"]}-warmup-dagger.trace.jsonl'
    spans = {}
    for line in trace.read_text().splitlines():
        row = json.loads(line)
        if row['kind']=='span' and row.get('endNs',0)>=spans.get(row['spanId'],{}).get('endNs',0):
            spans[row['spanId']]=row
    creating = [s for s in spans.values() if s['name']=='creating client' and s.get('scope')=='dagger.io/engine.client']
    assert len(creating)==1
    creating = creating[0]
    point['creating_client_ms']=(creating['endNs']-creating['startNs'])/1e6
    infos=sorted((s for s in spans.values() if s['name']=='moby.buildkit.v1.Control/Info' and s.get('parentId')==creating['spanId']),key=lambda s:s['startNs'])
    assert len(infos)>=2
    # The frozen OTLP receiver emits statusMsg; the extractor preserves raw records.
    point['info_calls']=[dict(start_ns=s['startNs'],end_ns=s['endNs'],ms=(s['endNs']-s['startNs'])/1e6,
        status=s.get('status'),description=s.get('statusMsg'),attrs=s.get('attrs',{})) for s in infos]
    point['info_error_count']=sum(s.get('status')=='STATUS_CODE_ERROR' for s in infos)
    point['info_total_ms']=sum(s['ms'] for s in point['info_calls'])
    point['info_gaps_ms']=[(b['startNs']-a['endNs'])/1e6 for a,b in zip(infos,infos[1:])]
    point['info_gap_ms']=sum(point['info_gaps_ms'])
    # Identical CLI behavior: queued Wait probe and existing version Info.
    # This is a semantic/trace gate, never a required latency improvement.
    assert len(infos)==2 and point['info_error_count']==0
    assert all(s.get('attrs',{}).get('rpc.grpc.status_code')==0 for s in infos)
    point['info_first_ms']=point['info_calls'][0]['ms']
    point['info_version_ms']=point['info_calls'][1]['ms']
    connects=[s for s in r['root_children'] if s['name']=='connect']
    assert len(connects)==1
    point['connect_ms']=connects[0]['ms']
    overlap=[s for s in r['image_progress']['layer_overlap'] if s['item']==largest]
    assert len(overlap)==1 and overlap[0]['read_before_own_download_end']
    point['largest_layer_overlap']=overlap[0]
    for key,argv0 in (('dpkg_ms','sh'),('rustup_ms','rustup')):
        execs=[e for e in r['execs'] if e['argv'][0]==argv0 and (argv0!='sh' or 'dpkg -i' in e['argv'][-1])]
        assert len(execs)==1
        point[key]=execs[0]['ms']
    samples.append(point)
assert len(samples)==6
pairs=[]
for index in range(3):
    pair={r['side']:r for r in samples[index*2:index*2+2]}
    assert set(pair)=={'A','B'}
    pairs.append({'pair':index,**{k:pair['A'][k]-pair['B'][k] for k in fields}})
result={'scope':__doc__,'phase_contract_pass':True,'samples':samples,'pairs_saved_ms':pairs,
    'paired_median_saved_ms':{k:statistics.median(r[k] for r in pairs) for k in fields},
    'limits':['Same CLI and verified-stream implementation; engine images differ only by the Unix helper and its tests; full official gzip Rust content in both',
              'Cold profiling and registry variability retained; not a full-install measurement',
              'First command includes ordinary CLI engine provisioning; debug helper copied only after that timer closes',
              'No controlled artificial readiness delay; fast-start samples remain in results',
              'Both treatments retain two successful Info calls: readiness and existing version validation',
              'Info duration includes local helper readiness, transport setup/backoff and RPC execution; it is not pure queue or CPU time',
              'Configured gRPC backoff can remain; no startup gap or positive savings is required to pass',
              'Do not sum phase medians or attribute image/network variation to this Unix helper change']}
with (OWNER/'phases.json').open('x') as out:
    json.dump(result,out,indent=2);out.write('\n')
print(json.dumps(result,indent=2))
