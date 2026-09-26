from pathlib import Path
import json
out=Path('/tmp/collections-perf/deferred-defaults/fixtures')
producer='''type Producer {
  source: Directory!
  new(source: Directory! @defaultPath("/"), constructorFail: Boolean! = false) {
    self.source = source
    if (constructorFail) { raise "constructor sentinel" } else { self }
  }
  pub base: Container! {
    if (source.file("body.txt").contents == "fail") { raise "body sentinel" } else {
    let server = container.from("alpine:3.23")
      .withDirectory("/www", source.directory("payload"))
      .withExposedPort(8080)
      .withExec(["httpd", "-f", "-p", "8080", "-h", "/www"])
      .asService
    container.from("alpine:3.23")
      .withFile("/value.txt", source.file("payload/value.txt"))
      .withServiceBinding("fixture", server)
    }
  }
  pub wrong: String! { "wrong type" }
}
'''
producer_go='''package main
import("context";"fmt";"dagger/producer/internal/dagger")
type Producer struct{Source *dagger.Directory}
func New(
 // +optional
 // +defaultPath="/"
 source *dagger.Directory,
 // +default=false
 constructorFail bool,
)(*Producer,error){if constructorFail{return nil,fmt.Errorf("constructor sentinel")};return &Producer{Source:source},nil}
func(m *Producer) Base(ctx context.Context)(*dagger.Container,error){
 mode,err:=m.Source.File("body.txt").Contents(ctx);if err!=nil{return nil,err};if mode=="fail"{return nil,fmt.Errorf("body sentinel")}
 service:=dag.Container().From("alpine:3.23").WithDirectory("/www",m.Source.Directory("payload")).WithExposedPort(8080).WithExec([]string{"httpd","-f","-p","8080","-h","/www"}).AsService()
 return dag.Container().From("alpine:3.23").WithFile("/value.txt",m.Source.File("payload/value.txt")).WithServiceBinding("fixture",service),nil
}
func(*Producer) Wrong()string{return "wrong type"}
'''
producer_ts='''import {dag, Directory, Container, object, field, func, argument} from "@dagger.io/dagger"
@object()
export class Producer {
 @field() source: Directory
 constructor(@argument({defaultPath:"/"}) source: Directory, constructorFail: boolean = false){
  if(constructorFail)throw new Error("constructor sentinel")
  this.source=source
 }
 @func() async base(): Promise<Container>{
  if(await this.source.file("body.txt").contents()==="fail")throw new Error("body sentinel")
  const service=dag.container().from("alpine:3.23").withDirectory("/www",this.source.directory("payload")).withExposedPort(8080).withExec(["httpd","-f","-p","8080","-h","/www"]).asService()
  return dag.container().from("alpine:3.23").withFile("/value.txt",this.source.file("payload/value.txt")).withServiceBinding("fixture",service)
 }
 @func() wrong():string{return "wrong type"}
}
'''
go='''package main
import (
 "context"
 "dagger/consumer/internal/dagger"
)
type Consumer struct { Base *dagger.Container }
func New(base *dagger.Container) *Consumer { return &Consumer{Base:base} }
func (*Consumer) Unused() string { return "unused" }
func (m *Consumer) Used(ctx context.Context) (string,error) { return m.Base.WithExec([]string{"sh","-c","cat /value.txt; wget -qO- http://fixture:8080/value.txt"}).Stdout(ctx) }
func (m *Consumer) Returned() *dagger.Container { return m.Base }
func (*Consumer) Items() *Items {return &Items{Names:[]string{"a","b"}}}
// +collection
type Items struct {
 // +keys
 Names []string
}
// +get
func (*Items) Get(key string) *Item {return &Item{Key:key}}
type Item struct{Key string}
// +check
func (*Item) Verify() error{return nil}
'''
ts='''import {Container, object, field, func, collection, keys, get, check} from "@dagger.io/dagger"
@object()
export class Consumer {
 @field() base: Container
 constructor(base: Container) { this.base = base }
 @func() unused(): string { return "unused" }
 @func() used(): Promise<string> { return this.base.withExec(["sh","-c","cat /value.txt; wget -qO- http://fixture:8080/value.txt"]).stdout() }
 @func() returned(): Container { return this.base }
 @func() items(): Items { return new Items() }
}
@collection()
export class Items {
 @keys() names: string[] = ["a","b"]
 @get() get(key: string): Item { return new Item(key) }
}
@object()
export class Item {
 @field() key: string
 constructor(key: string) { this.key = key }
 @check() verify(): void {}
}
'''
dang='''type Consumer {
  pub base: Container!
  new(base: Container!) {
    self.base = base
    self
  }
  pub unused: String! { "unused" }
  pub used: String! { base.withExec(["sh", "-c", "cat /value.txt; wget -qO- http://fixture:8080/value.txt"]).stdout }
  pub returned: Container! { base }
  pub items: Items! { Items(names: ["a", "b"]) }
}
type Items @collection {
  pub names: [String!]! @keys
  get(key: String!): Item! @get { Item(key: key) }
}
type Item {
  pub key: String!
  pub verify: Void @check { null }
}
'''
config='''[modules.producer]
source = "producer"
[modules.producer.settings]
constructor-fail = false
[modules.consumer]
source = "consumer"
entrypoint = true
[modules.consumer.settings]
base = "dag://producer/base"
'''
for sdk,source,name in [('go',go,'main.go'),('typescript',ts,'src/index.ts'),('dang',dang,'main.dang')]:
 root=out/sdk
 producer_source={'go':producer_go,'typescript':producer_ts,'dang':producer}[sdk]
 files={'dagger.toml':config,'producer/'+name:producer_source,
 'producer/dagger.json':json.dumps({'name':'producer','engineVersion':'v1.0.0','sdk':{'source':sdk}},indent=2),
 'consumer/dagger.json':json.dumps({'name':'consumer','engineVersion':'v1.0.0','sdk':{'source':sdk}},indent=2),
 'consumer/'+name:source,'constructor.txt':'ok','body.txt':'ok','payload/value.txt':'one\n'}
 if sdk=='typescript':
  files['consumer/package.json']='{"type":"module","dependencies":{"typescript":"^5.5.4"}}\n'
  files['consumer/tsconfig.json']=Path('/home/dagger/dag/core/integration/testdata/modules/typescript/optional-defaults/tsconfig.json').read_text()
  files['producer/package.json']=files['consumer/package.json'];files['producer/tsconfig.json']=files['consumer/tsconfig.json']
 for relative,contents in files.items():
  path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
print(out)
