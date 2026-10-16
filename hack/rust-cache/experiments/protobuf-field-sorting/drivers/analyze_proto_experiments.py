from pathlib import Path
import json,statistics

base=Path('/tmp/rust-cache-sipsma-review')
for name in ['small-proto-fields','typed-proto-fields']:
    root=base/name
    summaries={}
    all_samples=[]
    for cohort in ['commands','confirmation']:
        samples=[dict(row,cohort=cohort) for row in json.loads((root/cohort/'samples.json').read_text()) if not row['warmup']]
        all_samples.extend(samples)
    for kind in ['large','direct','tests','list']:
        pairs=[]
        for cohort in ['commands','confirmation']:
            for n in range(8):
                byarm={r['arm']:r for r in all_samples if r['cohort']==cohort and r['pair']==n and r['kind']==kind}
                a,b=byarm['before'],byarm['after']
                pairs.append(dict(cohort=cohort,pair=n,seconds_saved=a['command_seconds']-b['command_seconds'],bytes_saved=a['heap_delta']['TotalAlloc']-b['heap_delta']['TotalAlloc'],engine_cpu_saved=a['cpu_seconds']['engine']-b['cpu_seconds']['engine']))
        rows=[r for r in all_samples if r['kind']==kind]
        summaries[kind]=dict(pairs=pairs,median_paired_seconds_saved=statistics.median(r['seconds_saved'] for r in pairs),faster_pairs=sum(r['seconds_saved']>0 for r in pairs),median_paired_bytes_saved=statistics.median(r['bytes_saved'] for r in pairs),lower_allocation_pairs=sum(r['bytes_saved']>0 for r in pairs),median_paired_engine_cpu_saved=statistics.median(r['engine_cpu_saved'] for r in pairs),max_stall_fraction={k:max(r['stall_fraction'][k] for r in rows) for k in rows[0]['stall_fraction']},cache_collection_overlaps=sum(bool(r['completed_collection_overlaps']) for r in rows))
    (root/'pooled-summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    (root/'status.json').write_text(json.dumps(dict(status='not selected',reason='Component sorting and allocation gains do not establish a consistent complete edited-command speedup. Native compiler reuse remains intact.',ready_Dagger_proposals=8,new_PR_opened=False,library_patch_only=True,selected_engine='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721'),indent=2)+'\n')
    print(name,{k:{key:r[key] for key in ['median_paired_seconds_saved','faster_pairs','median_paired_bytes_saved','lower_allocation_pairs']} for k,r in summaries.items()})
root=base/'bulk-proto-json'
(root/'status.json').write_text(json.dumps(dict(status='rejected at component screen',reason='The fixture is slower and adds three allocations despite slightly fewer bytes. No engine installed and no complete-command latency claim.',baseline_source='Selected engine span.go overlay; original Protobuf v1.36.11 dependency.',new_PR_opened=False),indent=2)+'\n')
