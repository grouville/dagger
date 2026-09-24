from pathlib import Path
import os,subprocess,time,json
base=Path('/tmp/collections-perf/syntax-isolated');env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
env.update({'DAGGER_ENGINE':'container://dagger-engine.collections-syntax-cache','_EXPERIMENTAL_DAGGER_CLI_BIN':'/tmp/collections-perf/committed/dagger','DAGGER_SRC_ROOT':'/home/dagger/dag','DAGGER_BIN_ROOT':'/tmp/collections-perf/committed'})
rows=[]
commands=[
 ('dang-library',['go','test','./pkg/dang','-count=1'],str(base/'dang'),{}),
 ('syntax-cache-race',['go','test','-race','./pkg/dang','-run','^TestSyntaxCache','-count=1'],str(base/'dang'),{}),
 ('parse-versus-clone',['go','test','./pkg/dang','-run','^$','-bench','^BenchmarkSyntaxCacheAB$','-benchmem','-count=3'],str(base/'dang'),{'CGO_ENABLED':'0','DAGGER_DANG_BENCH_ROOT':'/tmp/dagger-go-discovery'}),
 ('dang-boundaries',['go','test','-v','./core/integration','-count=1','-parallel=1','-run','^(TestDang|TestDangForcing)$/(TestDirectives|TestSDKClientAttachables|TestWorkspaceArg|TestVersionedSyntax|TestSelfCallReturningOwnType|TestLazyChainForcing|TestLoadErrorReport)$'],'/home/dagger/dag',{}),
 ('collections',['go','test','-v','./core/integration','-count=1','-parallel=1','-run','^TestCollections$/(TestCommandLists|TestCheckSelection|TestDimensionItems|TestBatchReplacement)$'],'/home/dagger/dag',{}),
]
for name,args,cwd,extra in commands:
 start=time.monotonic()
 with (base/(name+'.log')).open('w') as out:p=subprocess.run(args,cwd=cwd,env=env|extra,stdout=out,stderr=subprocess.STDOUT)
 row={'name':name,'exit_code':p.returncode,'seconds':time.monotonic()-start,'command':args,'cwd':cwd}
 rows.append(row);print(json.dumps(row),flush=True);(base/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
 if p.returncode:raise SystemExit(p.returncode)
