from pathlib import Path
import hashlib,json,os,re,shutil,statistics,subprocess,time

root=Path(__file__).parent
repo=Path('/home/dagger/dagger_otra')
worktree=Path('/tmp/dagger-span-lookup-fanout-upstream')
base='717589c9ccacbba7d3cf902647aa5c9ca68085e8'
branch='perf/upstream-span-lookup-fanout'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
assert (root/'confirmation/summary.json').is_file(),'finish command measurements before creating a worktree'
assert subprocess.check_output(['git','show',base+':engine/clientdb/telemetry_store.go'],cwd=repo)==(root/'before.go').read_bytes()
subprocess.run(['git','worktree','add','--quiet','-b',branch,str(worktree),base],cwd=repo,check=True)
shutil.copyfile(root/'after.go',worktree/'engine/clientdb/telemetry_store.go')
shutil.copyfile(root/'upstream_test.go',worktree/'engine/clientdb/span_lookup_fanout_test.go')
overlay={'Replace':{str(worktree/'engine/clientdb/telemetry_store.go'):str(root/'before.go')}}
(root/'upstream-before-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
phases=[]
def run(label,command,env=None):
    tick=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(command,cwd=worktree,stdout=stream,stderr=subprocess.STDOUT,env=env)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-tick));(root/'upstream-validation.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,r.returncode,round(phases[-1]['seconds'],2),flush=True);assert r.returncode==0,label
run('upstream-baseline-compatibility',[go,'test','-p','1','-overlay',str(root/'upstream-before-overlay.json'),'./engine/clientdb','-run','^TestSpanLookupRepeatedIDsAndLateEdges$','-count=1'])
run('upstream-race',[go,'test','-p','1','-race','./engine/clientdb','-count=1'])
for arm in ['before','after']:
    command=[go,'test','-p','1']
    if arm=='before':command+=['-overlay',str(root/'upstream-before-overlay.json')]
    run('upstream-'+arm+'-build',command+['-c','-o',str(root/('upstream-'+arm+'.test')),'./engine/clientdb'])
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
samples=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'upstream-bench-{pair}-{arm}';before=pressure();tick=time.monotonic()
        run(label,[str(root/('upstream-'+arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkSpanLookupFanout$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'))
        elapsed=time.monotonic()-tick;after=pressure();values=[]
        for line in (root/(label+'.log')).read_text().splitlines():
            m=re.match(r'BenchmarkSpanLookupFanout/(parent|cause)/(\d+)-\d+\s+\d+\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op',line)
            if m:
                kind,count,ns,allocated,allocations=m.groups();values.append(dict(kind=kind,count=int(count),ns=float(ns),bytes=float(allocated),allocations=float(allocations)))
        assert len(values)==10,(label,len(values))
        samples.append(dict(pair=pair,arm=arm,seconds=elapsed,values=values,stall_fraction={k:(after[k]-before[k])/elapsed/1e6 for k in before}));(root/'upstream-component-runs.json').write_text(json.dumps(samples,indent=2)+'\n')
summary={}
for kind in ['parent','cause']:
    summary[kind]={}
    for count in [1,16,128,1026,4096]:
        summary[kind][count]={}
        for arm in ['before','after']:
            values=[v for s in samples if s['arm']==arm for v in s['values'] if v['kind']==kind and v['count']==count]
            summary[kind][count][arm]={k:statistics.median(v[k] for v in values) for k in ['ns','bytes','allocations']}
(root/'upstream-component-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
subprocess.run(['git','add','--','engine/clientdb/telemetry_store.go','engine/clientdb/span_lookup_fanout_test.go'],cwd=worktree,check=True)
subprocess.run(['git','diff','--cached','--check'],cwd=worktree,check=True)
subprocess.run(['git','-c','commit.gpgsign=false','commit','--quiet','-s','-m','perf: avoid quadratic span indexing'],cwd=worktree,check=True)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=worktree,text=True).strip()
(root/'upstream-branch.json').write_text(json.dumps(dict(base=base,head=head,branch=branch,branch_url='https://github.com/grouville/dagger/tree/'+branch,production_files=1,test_files=1,pr_opened=False),indent=2)+'\n')
print('Prepared standalone',head,branch,flush=True)
subprocess.run(['git','push','https://github.com/grouville/dagger.git','HEAD:'+branch],cwd=worktree,check=True)
print('Pushed to fork; no PR opened',flush=True)
