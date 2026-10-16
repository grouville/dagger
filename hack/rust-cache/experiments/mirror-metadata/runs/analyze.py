from pathlib import Path
import difflib,gzip,json,re,statistics

root=Path(__file__).parent
def benchmarks(folder,pattern,arms):
    result={}
    for size in [128,1026]:
        values={arm:[] for arm in arms}
        for pair in range(6):
            for arm in arms:
                text=(folder/f'bench-{pair}-{arm}.log').read_text()
                m=re.search(r'BenchmarkMirrorMetadataWalk/'+str(size)+'/'+pattern+str(arm).lower()+r'-\d+\s+\d+\s+(\d+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',text)
                assert m,(folder,pair,arm,size)
                values[arm].append(dict(pair=pair,ns=int(m[1]),bytes=int(m[2]),allocations=int(m[3])))
        result[str(size)]=dict(samples=values,median={str(arm):{key:statistics.median(r[key] for r in rows) for key in ['ns','bytes','allocations']} for arm,rows in values.items()})
    return result

component=benchmarks(root,'skip=',[False,True])
default=benchmarks(root/'default-cost','reference=',[True,False])
(root/'component-analysis.json').write_text(json.dumps(component,indent=2)+'\n')
(root/'default-cost/analysis.json').write_text(json.dumps(default,indent=2)+'\n')
phases=[]
for sample in json.loads((root/'phase-comparison/samples.json').read_text()):
    with gzip.open(root/f"phase-comparison/{sample['run']}-import-spans.json.gz",'rt') as stream:spans=json.load(stream)
    imports=[s for s in spans if s['name']=='uploading /tmp/rust-native-config-entry-1026-before'];assert len(imports)==1
    imp=imports[0];copies=[s for s in spans if s['name']=='copy' and s['parentId']==imp['spanId']];assert len(copies)==1
    copy=copies[0]
    phases.append(dict(run=sample['run'],policy=sample['mirror_policy'],before_copy_ms=(copy['startNs']-imp['startNs'])/1e6,copy_ms=(copy['endNs']-copy['startNs'])/1e6,import_ms=(imp['endNs']-imp['startNs'])/1e6,command_seconds=sample['command_seconds']))
phase_analysis=dict(samples=phases,median={arm:{key:statistics.median(r[key] for r in phases if r['policy']==arm) for key in ['before_copy_ms','copy_ms','import_ms','command_seconds']} for arm in ['before','after']},note='All four balanced pairs retained, including the first slow-copy baseline. The before-copy phase does not include that copy outlier. Captured spans have valid completed timestamps; streaming updates are excluded. These are phase diagnostics, not the null-receiver full-command cohort.')
(root/'phase-comparison/analysis.json').write_text(json.dumps(phase_analysis,indent=2)+'\n')
source=Path('/tmp/dagger-filesync-snapshot-seeds')
patch=''
for relative,name in [('internal/fsutil/fs.go','fs.go'),('internal/fsutil/stat.go','stat.go'),('engine/filesync/localfs.go','localfs.go')]:
    before=(source/relative).read_text();after=(root/name).read_text().replace('mirrorMetadataSkipXattrs.Load()','true')
    patch+=''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='a/'+relative,tofile='b/'+relative))
(root/'candidate.patch').write_text(patch)
(root/'status.json').write_text(json.dumps(dict(status='not selected',ready_upstream_proposals=8,new_pr_opened=False,selected_baseline_unchanged=True,reason='The faster engine-owned mirror walk does not establish a faster complete build. Direct phase captures leave almost all pre-copy elapsed time in place; the new option also adds allocation to ordinary default walks.',correctness='Focused cold/warm/edit/chmod/hash-repair compatibility, full affected package suites, candidate race suite, and six strict native histories pass.',limitations=['Four fresh-edit command kinds, eight paired comparisons each, on generated path-dependency workspaces, Rust 1.77.2.','Complete checks have uneven ordinary Go-GC counts; they establish no isolated compiler regression or improvement.','Component/default-layout controls have no process-pressure capture; they are screening evidence.','Seed depth was not emitted in source-import spans; slow full-copy attribution is inferred, not directly labeled.'],next='Profile the sender/receiver and diff path before copying, and the still-high complete collection-listing allocations. Do not optimize an overlapped component from CPU totals alone.'),indent=2)+'\n')
print('components',json.dumps({k:v['median'] for k,v in component.items()}))
print('default',json.dumps({k:v['median'] for k,v in default.items()}))
print('phases',json.dumps(phase_analysis['median']))
