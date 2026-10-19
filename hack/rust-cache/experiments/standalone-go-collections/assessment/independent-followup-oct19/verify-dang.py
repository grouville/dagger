from pathlib import Path
import hashlib,json,os,re,statistics,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19')
repo=Path('/tmp/go-collection-clean-dang')
base='bf649b8dd99f321984bc9cd9d1a3494acf2c0c39'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off')
paths={'main':out/'dang-main','typed-methods':Path('/tmp/go-collection-clean-branches/remaining-verification/dang-typed-methods'),'callback-caller':Path('/tmp/go-collection-clean-branches/remaining-verification/dang-callback-caller')}
if not paths['main'].exists():
 subprocess.run(['git','-c','gc.auto=0','-C',str(repo),'worktree','add','--detach',str(paths['main']),base],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
bench=r'''package dang

import (
 "context"
 "fmt"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func BenchmarkTypedMethodConstruction(b *testing.B) {
 for _, methods := range []int{0, 1, 32} {
  b.Run(fmt.Sprintf("methods=%d", methods), func(b *testing.B) {
   var source strings.Builder
   source.WriteString("type Owner { path: String!\n")
   for i := range methods { fmt.Fprintf(&source, `method%d(prefix: String! = "default"): String! { prefix + path }`+"\n", i) }
   source.WriteString("}\n")
   dir := b.TempDir()
   if err := os.WriteFile(filepath.Join(dir,"main.dang"), []byte(source.String()),0600); err != nil { b.Fatal(err) }
   ctx := context.Background()
   env, err := RunDir(ctx,dir,false); if err != nil { b.Fatal(err) }
   ctor, found, err := env.Lookup(ctx,"Owner"); if err != nil || !found { b.Fatalf("constructor: %t: %v",found,err) }
   args := map[string]Value{"path":StringValue{Val:"module/current"}}
   b.ReportAllocs(); b.ResetTimer()
   for range b.N {
    if _, err := ctor.(*ConstructorFunction).Call(ctx,env,args); err != nil { b.Fatal(err) }
   }
  })
 }
}

func BenchmarkCallbackCustomCaller(b *testing.B) {
 fn := &mutableCallback{}
 b.ReportAllocs(); b.ResetTimer()
 for range b.N { if _, err := callFunc(context.Background(),fn,IntValue{Val:1}); err != nil { b.Fatal(err) } }
}
'''.replace('\\\"','\"')
callback=(paths['callback-caller']/'pkg/dang/callback_caller_test.go').read_bytes()
typed=(paths['typed-methods']/'pkg/dang/coerced_method_hoisting_test.go').read_bytes()
for name,path in paths.items():
 (path/'pkg/dang/review_construction_bench_test.go').write_text(bench)
 (path/'pkg/dang/callback_caller_test.go').write_bytes(callback)
 if name=='main':(path/'pkg/dang/coerced_method_hoisting_test.go').write_bytes(typed)
steps=[]
def run(label,command,cwd,expected=0,needle=None):
 print(json.dumps(dict(event='start',label=label)),flush=True);start=time.monotonic()
 with (out/(label+'.log')).open('w') as log:
  r=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 text=(out/(label+'.log')).read_text()
 okay=r.returncode==expected if expected==0 else r.returncode!=0 and needle in text and 'build failed' not in text
 row=dict(label=label,command=command,cwd=str(cwd),seconds=time.monotonic()-start,exit_code=r.returncode,verified=okay,log=label+'.log');steps.append(row)
 (out/'dang-checks.json').write_text(json.dumps(steps,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 if not okay:raise RuntimeError(text[-3500:])
 return text
run('typed-methods-current-main-negative',[go,'test','-p=2','-count=1','-run','^TestCoercedMethodsAvoidVariableInitializers$','./pkg/dang'],paths['main'],expected=1,needle='typed methods must be installed without variable initializers')
for name,path in paths.items():
 run(name+'-build-benchmark',[go,'test','-p=2','-c','-o',str(out/(name+'.test')),'./pkg/dang'],path)
# Compile all variants before measuring, then run strictly sequential alternating pairs.
samples=[]
for proposal,pattern in [('typed-methods','^BenchmarkTypedMethodConstruction$'),('callback-caller','^BenchmarkCallback(Caller|CustomCaller)$')]:
 for pair in range(6):
  for arm in (['main',proposal] if pair%2==0 else [proposal,'main']):
   label=f'{proposal}-{pair}-{arm}'
   pressure=Path('/proc/pressure/cpu').read_text()
   text=run(label,[str(out/(arm+'.test')),'-test.run=^$','-test.bench='+pattern,'-test.benchmem','-test.benchtime=300ms','-test.count=1'],paths[arm])
   for line in text.splitlines():
    m=re.match(r'(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
    if m:samples.append(dict(proposal=proposal,pair=pair,arm=arm,benchmark=m[1],iterations=int(m[2]),ns=float(m[3]),bytes=int(m[4]),allocs=int(m[5]),cpu_pressure=pressure))
   (out/'dang-samples.json').write_text(json.dumps(samples,indent=2)+'\n')
summary=[]
for proposal in ['typed-methods','callback-caller']:
 for benchmark in sorted({r['benchmark'] for r in samples if r['proposal']==proposal}):
  a=sorted([r for r in samples if r['proposal']==proposal and r['benchmark']==benchmark and r['arm']=='main'],key=lambda r:r['pair'])
  b=sorted([r for r in samples if r['proposal']==proposal and r['benchmark']==benchmark and r['arm']==proposal],key=lambda r:r['pair'])
  assert len(a)==len(b)==6
  summary.append(dict(proposal=proposal,benchmark=benchmark,before_ns=statistics.median(r['ns'] for r in a),candidate_ns=statistics.median(r['ns'] for r in b),before_bytes=statistics.median(r['bytes'] for r in a),candidate_bytes=statistics.median(r['bytes'] for r in b),before_allocs=statistics.median(r['allocs'] for r in a),candidate_allocs=statistics.median(r['allocs'] for r in b),faster_pairs=sum(y['ns']<x['ns'] for x,y in zip(a,b))))
(out/'dang-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(event='complete',summary=summary)),flush=True)
