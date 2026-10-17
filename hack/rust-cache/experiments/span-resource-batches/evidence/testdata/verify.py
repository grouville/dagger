from pathlib import Path
import json,os,subprocess,time
r=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='4',GOTOOLCHAIN='local')
module=str(r.parent/'dang-native-string-sort/engine.go.mod')
selection='^(TestSpanResourceBatch|TestSpanResourceBatchConcurrentExports|TestTelemetryRoutesClientsAndAncestorsExactlyOnce|TestTelemetryStreamFramesBatchesAndDrain|TestSessionDeliversCallSpansToStoreAndCloud)$'
jobs=[]
for arm,race in [('before',False),('after',False),('after',True)]:
 args=['test','-p','2','-buildvcs=false','-modfile',module,'-overlay',str(r/('overlay-'+arm+'.json')),'-count=1','-run',selection]
 if race:args.append('-race')
 jobs.append((arm+('-race' if race else '-tests'),args+['./engine/server']))
for i,arm in enumerate(['before','after','after','before']):
 jobs.append((str(i)+'-'+arm+'-benchmark',['test','-p','2','-buildvcs=false','-modfile',module,'-overlay',str(r/('overlay-'+arm+'.json')),'-run','^$','-bench','^BenchmarkSpanResourceBatch$','-benchmem','-benchtime=100ms','-count=2','./engine/server']))
rows=[]
for label,args in jobs:
 tick=time.monotonic();cmd=[go,*args]
 with (r/(label+'.log')).open('w') as out:result=subprocess.run(cmd,cwd='/tmp/dagger-filesync-snapshot-seeds',env=env,stdout=out,stderr=subprocess.STDOUT)
 row=dict(label=label,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode);rows.append(row);(r/'checks.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 assert result.returncode==0,label
