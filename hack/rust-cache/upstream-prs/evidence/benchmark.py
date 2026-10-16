#!/usr/bin/env python3
"""Build both arms with identical tests, then run six alternating paired processes."""
import argparse, datetime, hashlib, json, os, pathlib, platform, statistics, subprocess, time
ROOT = pathlib.Path(__file__).resolve().parent
GO = '/home/dagger/.local/bin/go'
NAMES = ['primitive-owners','primitive-encoding','cache-usage-maps','artifact-list-output','collection-key-index']
ENV = dict(os.environ, GOMAXPROCS='8')

def write_json(p, value):
    p.write_text(json.dumps(value, indent=2)+'\n')

def execute(args, cwd, log, expected=0):
    start = time.time()
    with log.open('w') as f:
        r = subprocess.run(args,cwd=cwd,env=ENV,stdout=f,stderr=subprocess.STDOUT)
    if r.returncode != expected:
        raise RuntimeError(f'{args}: exit {r.returncode}, expected {expected}; {log}')
    return dict(command=args,seconds=time.time()-start,exit_code=r.returncode,log=str(log))

def parse(log):
    rows = {}
    for line in log.read_text().splitlines():
        if not line.startswith('Benchmark'):
            continue
        fields = line.split()
        if len(fields)<4:
            continue
        try:
            n = int(fields[1])
            metrics = {fields[i+1]:float(fields[i]) for i in range(2,len(fields)-1,2)}
        except ValueError:
            continue
        rows[fields[0].rsplit('-',1)[0]]=dict(iterations=n,**metrics)
    if not rows:
        raise RuntimeError(f'No benchmark rows in {log}')
    return rows

def pressure():
    return {p.name:p.read_text() for p in pathlib.Path('/proc/pressure').iterdir()}

p = argparse.ArgumentParser()
p.add_argument('mode',choices=['build','measure'])
p.add_argument('--name',choices=NAMES)
a=p.parse_args()
names = [a.name] if a.name else NAMES
for name in names:
    d=ROOT/name;c=json.loads((d/'config.json').read_text());w=pathlib.Path(c['worktree'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()
    if head != c['head'] or subprocess.check_output(['git','status','--porcelain'],cwd=w,text=True).strip():
        raise RuntimeError(f'Source changed: {w}')
    if a.mode=='build':
        replacements={}
        for source in c['production_files']:
            baseline=d/'main-source'/source
            baseline.parent.mkdir(parents=True,exist_ok=True)
            baseline.write_bytes(subprocess.check_output(['git','show',c['base']+':'+source],cwd=w))
            replacements[str(w/source)]=str(baseline)
        write_json(d/'before-overlay.json',{'Replace':replacements})
        builds=[]
        for arm in ['before','after']:
            args=[GO,'test','-c','-o',str(d/(arm+'.test'))]
            if arm=='before': args += ['-overlay='+str(d/'before-overlay.json')]
            args += [c['package']]
            builds.append(execute(args,w,d/(arm+'-build.log')))
        write_json(d/'builds.json',builds)
        # The unchanged main implementation must reproduce output loss.
        if name=='artifact-list-output':
            for arm,code in [('before',1),('after',0)]:
                execute([str(d/(arm+'.test')),'-test.run=^TestArtifactListOutputSurvivesLogBurst$','-test.count=1'],w,d/(arm+'-burst-test.log'),expected=code)
            for arm in ['before','after']:
                execute([str(d/(arm+'.test')),'-test.run=^TestArtifactListOutputWriteError$','-test.count=1'],w,d/(arm+'-write-error-test.log'))
        elif name=='primitive-owners':
            for arm in ['before','after']:
                execute([str(d/(arm+'.test')),'-test.run=^(TestInlinePrimitiveNamedOwner|TestPrimitiveArrayRequiresListDeclaration)$','-test.count=1'],w,d/(arm+'-compatibility-test.log'))
        elif name=='primitive-encoding':
            for arm in ['before','after']:
                execute([str(d/(arm+'.test')),'-test.run=^TestPersistedPrimitiveArrayEncoding$','-test.count=1'],w,d/(arm+'-compatibility-test.log'))
        elif name=='collection-key-index':
            for arm in ['before','after']:
                execute([str(d/(arm+'.test')),'-test.run=^TestArtifactDimensionKeysAncestors$','-test.count=1'],w,d/(arm+'-compatibility-test.log'))
        print('BUILT',name,flush=True)
        continue
    runs=[]
    context=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),go=subprocess.check_output([GO,'version'],text=True).strip(),platform=platform.platform(),gomaxprocs=8,cpu=next((x.split(':',1)[1].strip() for x in pathlib.Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),None),config=c,binary_sha256={arm:hashlib.sha256((d/(arm+'.test')).read_bytes()).hexdigest() for arm in ['before','after']})
    for pair in range(6):
        for arm in (['before','after'] if pair%2==0 else ['after','before']):
            log=d/f'pair-{pair+1}-{arm}.log'
            psi_before=pressure()
            args=[str(d/(arm+'.test')),'-test.run=^$','-test.bench=^'+c['benchmark'],'-test.benchmem','-test.benchtime='+c['benchtime'],'-test.count=1']
            run=execute(args,w,log)
            run.update(pair=pair+1,arm=arm,metrics=parse(log),pressure_before=psi_before,pressure_after=pressure())
            runs.append(run)
            write_json(d/'runs.json',dict(context=context,runs=runs))
        print('PAIR',name,pair+1,flush=True)
    cases={}
    if not all(set(x['metrics'])==set(runs[0]['metrics']) for x in runs):
        raise RuntimeError('Different benchmark cases across arms')
    for case in runs[0]['metrics']:
        arms={arm:[r['metrics'][case] for r in runs if r['arm']==arm] for arm in ['before','after']}
        stats={arm:{m:statistics.median(x[m] for x in arms[arm]) for m in arms[arm][0] if m!='iterations'} for arm in arms}
        delta=[arms['before'][i]['ns/op']-arms['after'][i]['ns/op'] for i in range(6)]
        cases[case]=dict(**stats,median_paired_saved_ns=statistics.median(delta),pairs_faster=sum(x>0 for x in delta),pairs=6)
    write_json(d/'summary.json',dict(context=context,cases=cases))
    print('DONE',name,flush=True)
