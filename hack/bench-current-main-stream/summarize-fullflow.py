#!/usr/bin/env python3
"""Summarize three independent CLI pairs; within-run repeats are not new pairs."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent
COHORT = Path(sys.argv[1]).resolve()

def stats(values):
    return dict(n=len(values), median=statistics.median(values), minimum=min(values), maximum=max(values), values=values)

def main():
    meta = json.loads((COHORT/'cohort.json').read_text())
    analysis = json.loads((COHORT/'analysis-r2/report.json').read_text())
    ordinary = json.loads((COHORT/'ordinary-exec-audit/report.json').read_text())
    assert ordinary['all_pass'] and len(ordinary['checks']) == 54
    assert meta['status']=='passed' and analysis['all_captures_pass']
    assert len(meta['runs'])==6 and len(analysis['profiles'])==36 and len(analysis['caches'])==18
    assert len(analysis['warm_rebuilds'])==36 and all(r['passed'] for r in analysis['warm_rebuilds'])
    result = dict(scope='Three independent AB/BA/AB matched engine pairs, same CLI and official gzip Rust image; stream/hash engine comparison; per-run warm repeats summarized first.',
        limits=['First check and external upgrade profiled; other timed scenarios omit --profile but export local OTLP',
                'Native uses docker exec in matched preinstalled image, not bare host',
                'Engine/CLI/native image and local module preinstalled; no full-install claim',
                'Default engine registry route, no diagnostic config or local registry',
                'Host page/CDN caches not purged; native follows Dagger for initial check',
                'Cargo diagnostic sessions occur after measured checks on both treatments',
                'The later application diagnostic follows failure/revisit/cached-repair and rebuilds three crates; ordinary timed application edits rebuild only ripgrep',
                'Three within-run samples are repeated observations, not nine independent pairs',
                'No artifact/fmt/clippy/test-command/macOS/remote performance claim'],
        cohorts=1, independent_pairs=3, profiles=36, cache_analyses=18, warm_rebuild_audits=36, ordinary_exec_audits=54,
        samples=[], scenarios={}, profiles_detail=analysis['profiles'])
    for entry in meta['runs']:
        root=Path(entry['root'])
        rows=list(csv.DictReader((root/'timings.csv').open()))
        first=json.loads((root/'first-use.json').read_text())
        flows={}
        for name, key in (('first-check','dagger_first_check_ms'),('provision-plus-first-check','dagger_provision_plus_first_check_ms')):
            dag=first[key]; native=first['native_first_check_ms']
            flows[name]=dict(profiled=True, samples=1, dagger_ms=dag,native_ms=native,
                overhead_ms=dag-native, ratio=dag/native, measurements=[dict(dagger_ms=dag,native_ms=native,overhead_ms=dag-native)])
        for name in ('exact','application','workspace-library','dependency-upgrade','dependency-followup'):
            selected=[r for r in rows if r['scenario']==name]
            indices=sorted({int(r['sample']) for r in selected})
            expected=3 if name in ('exact','application','workspace-library') else 1
            assert len(indices)==expected
            points=[]
            for index in indices:
                pair={r['side']:r for r in selected if int(r['sample'])==index}
                assert set(pair)=={'native','dagger'}
                profiled=name=='dependency-upgrade'
                assert pair['dagger']['profiled']==str(profiled) and pair['native']['profiled']=='False'
                dag=float(pair['dagger']['milliseconds']); native=float(pair['native']['milliseconds'])
                points.append(dict(sample=index,dagger_ms=dag,native_ms=native,overhead_ms=dag-native,ratio=dag/native))
            flows[name]=dict(profiled=profiled,samples=expected,
                **{key:statistics.median(p[key] for p in points) for key in ('dagger_ms','native_ms','overhead_ms','ratio')},measurements=points)
        result['samples'].append(dict(index=entry['index'],side=entry['side'],root=str(root),flows=flows))
    for name in result['samples'][0]['flows']:
        pairs=[]
        for index in range(3):
            pair={s['side']:s['flows'][name] for s in result['samples'][index*2:index*2+2]}
            assert set(pair)=={'A','B'}
            pairs.append(dict(pair=index,order='BA' if index==1 else 'AB',
                dagger_saved_ms=pair['A']['dagger_ms']-pair['B']['dagger_ms'],
                overhead_saved_ms=pair['A']['overhead_ms']-pair['B']['overhead_ms']))
        result['scenarios'][name]=dict(profiled=result['samples'][0]['flows'][name]['profiled'], pairs=pairs,
            paired={key:{**stats([p[key] for p in pairs]),'favorable':sum(p[key]>0 for p in pairs)}
                    for key in ('dagger_saved_ms','overhead_saved_ms')},
            marginal={side:{key:stats([s['flows'][name][key] for s in result['samples'] if s['side']==side])
                for key in ('dagger_ms','native_ms','overhead_ms','ratio')} for side in ('A','B')})
    with (ROOT/'summary.json').open('x') as out: json.dump(result,out,indent=2); out.write('\n')
    print(json.dumps({name:{'paired_cli_saved_ms':data['paired']['dagger_saved_ms'],
        'paired_overhead_saved_ms':data['paired']['overhead_saved_ms'],
        'candidate_ms':data['marginal']['B']['dagger_ms']['median'],
        'native_ms':data['marginal']['B']['native_ms']['median'],
        'overhead_ms':data['marginal']['B']['overhead_ms']['median']} for name,data in result['scenarios'].items()},indent=2))

if __name__=='__main__': main()
