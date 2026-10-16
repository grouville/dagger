from pathlib import Path
import hashlib,json,os,subprocess,time

root=Path(__file__).parent;out=root/'field-sorter-screen';out.mkdir(exist_ok=True)
source=Path('/tmp/protobuf-field-order-experiment')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
candidate=(root/'candidate.go').read_text()
needle='sort.Slice(fields, func(i, j int) bool { return less(fields[i].fd, fields[j].fd) })'
assert candidate.count(needle)==1
candidate=candidate.replace(needle,'sort.Sort(&messageFieldSorter{fields: fields, less: less})')
needle='// RangeFields iterates over the fields of fs according to the specified order.'
candidate=candidate.replace(needle,'''type messageFieldSorter struct {
    fields []messageField
    less FieldOrder
}
func (s *messageFieldSorter) Len() int { return len(s.fields) }
func (s *messageFieldSorter) Less(i,j int) bool { return s.less(s.fields[i].fd,s.fields[j].fd) }
func (s *messageFieldSorter) Swap(i,j int) { s.fields[i],s.fields[j] = s.fields[j],s.fields[i] }

'''+needle)
(out/'candidate.go').write_text(candidate)
subprocess.run(['gofmt','-w',str(out/'candidate.go')],check=True)
base=json.loads((root/'overlay.json').read_text())
for arm,path in [('before',root/'before.go'),('small',root/'candidate.go'),('interface',out/'candidate.go')]:
    overlay=json.loads(json.dumps(base));overlay['Replace'][str(source/'internal/order/range.go')]=str(path)
    (out/(arm+'.json')).write_text(json.dumps(overlay,indent=2)+'\n')
    for suite in ['order','clientdb']:
        command=[go,'test','-overlay',str(out/(arm+'.json'))]
        cwd=source
        if suite=='clientdb':command+=['-modfile',str(root/'engine.go.mod')];cwd=Path('/tmp/dagger-filesync-snapshot-seeds')
        command+=['-c','-o',str(out/(arm+'-'+suite+'.test')),'./internal/order' if suite=='order' else './engine/clientdb']
        with (out/('build-'+arm+'-'+suite+'.log')).open('w') as stream:subprocess.run(command,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True)
with (out/'reference-tests.log').open('w') as stream:subprocess.run([str(out/'interface-order.test'),'-test.run=TestSmallFieldsMatchReference|TestRangeFields','-test.count=1'],stdout=stream,stderr=subprocess.STDOUT,check=True)
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
rows=[]
orders=[['before','small','interface'],['interface','small','before'],['small','before','interface'],['interface','before','small'],['before','interface','small'],['small','interface','before']]
for pair,order in enumerate(orders):
    for suite,bench in [('order','^BenchmarkRangeFields$'),('clientdb','^BenchmarkMarshalProtoJSONs/current$')]:
        for arm in order:
            label=f'{pair}-{suite}-{arm}';before=pressure();started=time.monotonic()
            with (out/(label+'.log')).open('w') as stream:subprocess.run([str(out/(arm+'-'+suite+'.test')),'-test.run=^$','-test.bench='+bench,'-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT,check=True)
            seconds=time.monotonic()-started;after=pressure();metrics=[]
            for line in (out/(label+'.log')).read_text().splitlines():
                if line.startswith('Benchmark'):
                    f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
            rows.append(dict(pair=pair,suite=suite,arm=arm,seconds=seconds,metrics=metrics,stall_fraction={k:(after[k]-before[k])/seconds/1e6 for k in before}))
            (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('finished screen pair',pair,flush=True)
