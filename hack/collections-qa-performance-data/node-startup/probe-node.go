package main

import (
 "context"
 "fmt"
 "os"
 "time"
 "dagger.io/dagger"
)

func main() {
 ctx:=context.Background()
 dag,err:=dagger.Connect(ctx);if err!=nil{panic(err)};defer dag.Close()
 source:=dag.Host().Directory("/tmp/collections-perf/normal-baseline/greetings-split/.dagger/modules/frontend")
 tsx:=dag.Host().Directory("/tmp/collections-perf/ts-cache/extracted/tsx_module")
 ctr:=dag.Container().From("node:24.13.1-alpine@sha256:4f696fbf39f383c1e486030ba6b289a5d9af541642fc78ab197e584a113b9c03").
  WithMountedDirectory("/usr/local/lib/node_modules/tsx",tsx).
  WithDirectory("/src/.dagger/modules/frontend",source).
  WithWorkdir("/src/.dagger/modules/frontend").
  WithEnvVariable("TSX_TSCONFIG_PATH","/src/.dagger/modules/frontend/tsconfig.json").
  WithNewFile("/probe.mjs",`const start = performance.now();
await import("/src/.dagger/modules/frontend/sdk/index.ts");
console.log("sdk-import-ms", performance.now()-start);
await import("/src/.dagger/modules/frontend/src/index.ts");
console.log("total-import-ms", performance.now()-start);
`).WithDirectory("/profiles",dag.Directory())
 for _,variant:=range []string{"uncached","tsx","tsx-node"}{
  c:=ctr
  if variant!="uncached"{c=c.WithMountedCache("/tmp/tsx-0",dag.CacheVolume("profile-tsx-transforms"))}
  if variant=="tsx-node"{c=c.WithMountedCache("/root/.cache/dagger-node-compile",dag.CacheVolume("profile-node-compile")).WithEnvVariable("NODE_COMPILE_CACHE","/root/.cache/dagger-node-compile")}
  for i:=0;i<2;i++{
   exec:=c.WithEnvVariable("PROBE_NONCE",fmt.Sprint(time.Now().UnixNano())).WithExec([]string{"node","--import","/usr/local/lib/node_modules/tsx/dist/loader.mjs","--cpu-prof","--cpu-prof-dir=/profiles","/probe.mjs"})
   out,err:=exec.Stdout(ctx);if err!=nil{panic(err)};fmt.Println(variant,i,out)
   path:=fmt.Sprintf("/tmp/collections-perf/half-second/node-profiles/%s-%d",variant,i)
   if _,err:=exec.Directory("/profiles").Export(ctx,path);err!=nil{panic(err)}
  }
 }
 _=os.Stdout
}
