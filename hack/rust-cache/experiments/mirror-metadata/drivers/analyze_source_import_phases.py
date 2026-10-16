from pathlib import Path
import gzip,json,statistics

base=Path('/tmp/rust-cache-sipsma-review')
all_rows=[]
for folder in ['source-import-phases-current','source-import-phases-profile']:
    root=base/folder
    rows=[]
    for sample in json.loads((root/'samples.json').read_text()):
        n=sample['run']
        with gzip.open(root/f'{n}-import-spans.json.gz','rt') as stream:spans=json.load(stream)
        imports=[r for r in spans if r['name']=='uploading /tmp/rust-native-config-entry-1026-before']
        assert len(imports)==1,(folder,n,len(imports))
        imp=imports[0]
        copies=[r for r in spans if r['name']=='copy' and r['parentId']==imp['spanId']]
        assert len(copies)==1,(folder,n,len(copies))
        copy=copies[0]
        assert imp['startNs']<=copy['startNs']<=copy['endNs']<=imp['endNs']
        row=dict(run=n,profiled=folder.endswith('profile'),command_seconds=sample['command_seconds'],import_ms=(imp['endNs']-imp['startNs'])/1e6,before_copy_ms=(copy['startNs']-imp['startNs'])/1e6,copy_ms=(copy['endNs']-copy['startNs'])/1e6,after_copy_ms=(imp['endNs']-copy['endNs'])/1e6,import_span_id=imp['spanId'],copy_span_id=copy['spanId'],completed_spans=sample['completed_spans'],unfinished_updates_excluded=sample['unfinished_updates'],telemetry_window_bytes=sample['telemetry_bytes'])
        rows.append(row)
    summary=dict(samples=rows,median={k:statistics.median(r[k] for r in rows) for k in ['command_seconds','import_ms','before_copy_ms','copy_ms','after_copy_ms']},fast_copy_phase_count=sum(r['copy_ms']<100 for r in rows),slow_copy_phase_count=sum(r['copy_ms']>=100 for r in rows),note='Fast/slow classes are descriptive timing bands. Seed depth was not emitted in these captures. A slow copy phase is consistent with the bounded-seed full-copy fallback; its internal cause is inferred from implementation and prior full-copy measurements.')
    (root/'phase-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    all_rows.append(dict(folder=folder,**summary))
    print(folder,json.dumps(summary['median']),summary['fast_copy_phase_count'],summary['slow_copy_phase_count'])
(base/'source-import-phase-summary.json').write_text(json.dumps(all_rows,indent=2)+'\n')
