from pathlib import Path
import shutil
root=Path('/tmp/rust-cache-sipsma-review/plan-decode-libraries')
(root/'model').mkdir()
shutil.copy('/tmp/dagger-rust-native-deep-artifact-closures/compiler/model/model.go',root/'model/model.go')
(root/'go.mod').write_text('''module plan-decode-bench

go 1.26.6

require (
    github.com/goccy/go-json v0.11.2
    github.com/segmentio/encoding v0.5.4
)
''')
(root/'main.go').write_text(r'''package main

import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "flag"
    "fmt"
    "os"
    "reflect"
    "runtime"
    "time"

    fast "github.com/goccy/go-json"
    segment "github.com/segmentio/encoding/json"
    "plan-decode-bench/model"
)

func main() {
    mode := flag.String("mode", "standard", "decoder")
    path := flag.String("plan", "", "captured plan")
    validate := flag.Bool("validate", false, "compare edge cases with encoding/json")
    flag.Parse()
    decoders := map[string]func([]byte, any) error{"standard":json.Unmarshal, "goccy":fast.Unmarshal, "segmentio":segment.Unmarshal}
    decode := decoders[*mode]
    if decode == nil { panic("invalid decoder") }
    if *validate {
        cases := []string{
            `null`, `{}`, `{"version":1,"actions":null}`, `{"version":1,"actions":[]}`,
            `{"version":1,"actions":[{"id":"a","args":["x","y"],"env":{"A":"1","B":"2"}}]}`,
            `{"version":1,"actions":[{"id":"a","env":{"A":"1","A":"2"}}]}`,
            `{"version":1,"actions":[{"id":"a","args":["\ud800","\udc00","\ud83d\ude00"]}]}`,
            "{\"version\":1,\"actions\":[{\"id\":\"bad\xffutf8\"}]}",
            `{"version":1,"VERSION":2,"actions":[{"id":"a","compiler_seconds":0.10000000000000002}]}`,
            `{"version":1,"actions":[{"id":"a","id":null,"env":{"A":"1"},"env":null}]}`,
            `{"version":1,"actions":[{"id":"a"}],"unknown":{"deep":[{"nested":true}]}}`,
            `{"version":1} trailing`, `{"version":1}{}`, `{"version":"bad"}`, `{"version":1.5}`,
            `{"version":1,"actions":[{"args":[1]}]}`, `{"version":1,"actions":[{"compiler_seconds":1e999}]}`,
            `{"version":1,"actions":[{"id":"bad\x"}]}`, `{"version":1,}`, `{"version":1`,
        }
        for i, input := range cases {
            var reference, actual model.Plan
            re, ae := json.Unmarshal([]byte(input), &reference), decode([]byte(input), &actual)
            if (re==nil)!=(ae==nil) || (re==nil && !reflect.DeepEqual(reference,actual)) {
                panic(fmt.Sprintf("case %d mismatch: standard=%v actual=%v values=%#v / %#v",i,re,ae,reference,actual))
            }
        }
        fmt.Println("PASS",*mode,"20 decoder compatibility cases")
        return
    }
    contents, err := os.ReadFile(*path)
    if err != nil { panic(err) }
    var before, after runtime.MemStats
    runtime.ReadMemStats(&before)
    var plan model.Plan
    start := time.Now()
    if err := decode(contents,&plan); err != nil { panic(err) }
    elapsed := time.Since(start)
    runtime.ReadMemStats(&after)
    // Validation runs after the first-use decoder timer, so it cannot warm it.
    var expected model.Plan
    if err:=json.Unmarshal(contents,&expected);err!=nil {panic(err)}
    if !reflect.DeepEqual(plan,expected) {panic("decoded plan differs from encoding/json")}
    canonical, err := json.Marshal(plan)
    if err != nil {panic(err)}
    digest := sha256.Sum256(canonical)
    result := map[string]any{"decoder":*mode,"bytes":len(contents),"actions":len(plan.Actions),"seconds":elapsed.Seconds(),"allocated_bytes":after.TotalAlloc-before.TotalAlloc,"allocations":after.Mallocs-before.Mallocs,"go_gc_cycles":after.NumGC-before.NumGC,"canonical_sha256":hex.EncodeToString(digest[:])}
    if err:=json.NewEncoder(os.Stdout).Encode(result);err!=nil {panic(err)}
}
''')
print(root)
