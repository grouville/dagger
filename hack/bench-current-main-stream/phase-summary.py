#!/usr/bin/env python3
"""Offline mechanism gate and shared delivery envelope; not additive phase CPU."""
import json
from pathlib import Path
import statistics
import sys

OWNER = Path(__file__).resolve().parent
cohort = Path(sys.argv[1]).resolve(strict=True)
assert cohort.parent == Path('/tmp') and cohort.name.startswith('dagger-rust-current-stream-ab-')
report = json.loads((cohort/'analysis-r2/report.json').read_text())
assert report['all_captures_pass'] and report['cross_side_image_byte_sets_equal']
meta = report['metadata']
firsts = [r for r in report['profiles'] if r['label']=='warmup-dagger']
assert len(firsts)==6
largest = 'sha256:167b9fde7ea2106ff0349f834ad13f3d5078836087edf8a9422da759c088f66c'
fields = ('process_ms','cargo_ms','rust_delivery_envelope_ms','connect_ms','dpkg_ms','rustup_ms')
samples = []
for r in firsts:
    point = {key:r[key] for key in ('index','side','process_ms','cargo_ms','rust_delivery_envelope_ms','replay_drift')}
    connects = [s for s in r['root_children'] if s['name']=='connect']
    assert len(connects)==1
    point['connect_ms']=connects[0]['ms']
    # Deferred mode's preparation is metadata-only, not the baseline's full
    # pulling operation. Retain both names; never subtract these as peers.
    preps=[s for s in r['image_spans'] if s['name'] in (
        'pulling rust',
        'preparing pull rust')]
    assert len(preps)==1
    point['initial_pull_stage']=preps[0]
    unpack=[s for s in r['image_spans'] if s['name']=='unpacking rust']
    assert len(unpack)==1
    point['unpack_envelope']=unpack[0]
    streamed=[s for s in r['image_spans'] if s['name']=='streaming image layer into private snapshot '+largest]
    overlap=[s for s in r['image_progress']['layer_overlap'] if s['item']==largest]
    assert len(overlap)==1
    point['largest_layer_overlap']=overlap[0]
    point['largest_layer_stream_spans']=streamed
    if r['side']=='B':
        assert len(streamed)==1 and overlap[0]['read_before_own_download_end']
    else:
        assert not streamed and not overlap[0]['read_before_own_download_end']
    for key,argv0 in (('dpkg_ms','sh'),('rustup_ms','rustup')):
        execs=[e for e in r['execs'] if e['argv'][0]==argv0 and (argv0!='sh' or 'dpkg -i' in e['argv'][-1])]
        assert len(execs)==1
        point[key]=execs[0]['ms']
    samples.append(point)
pairs=[]
for index in range(3):
    pair={r['side']:r for r in samples[index*2:index*2+2]}
    assert set(pair)=={'A','B'}
    pairs.append({'pair':index, **{k:pair['A'][k]-pair['B'][k] for k in fields}})
result={'scope':__doc__, 'mechanism_gate_pass':True, 'samples':samples, 'pairs_saved_ms':pairs,
        'paired_median_saved_ms':{k:statistics.median(r[k] for r in pairs) for k in fields},
        'limits':['B emits preparing pull, not pulling; compare shared image delivery envelope',
                  'Cold phases measured with wcprof; replay drift retained, no what-if prediction',
                  'Shared delivery envelope includes all preparation/download/unpack work; preparation and unpack spans have different waiting semantics across engines',
                  'Do not sum medians or attribute all CLI delta to the image path; hash and streaming are a combined treatment',
                  'Progress proves compressed input consumed before its own download ends; actual private filesystem materialization is covered separately by correctness fixtures',
                  'Default engine registry configuration, same official gzip Rust image; no local-registry override; Docker/CLI/engine/native images/module preinstalled, not complete installation']}
with (OWNER/'phases.json').open('x') as out:
    json.dump(result,out,indent=2);out.write('\n')
print(json.dumps(result,indent=2))
