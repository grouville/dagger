from pathlib import Path
import hashlib,json,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'bulk-proto-json';root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds');previous=base/'parallel-fingerprint-engine'
overlay=json.loads((previous/'overlay.json').read_text())
logical=str(source/'engine/clientdb/span.go')
before=Path(overlay['Replace'][logical]).read_text()
(root/'before.go').write_text(before)
needle='func MarshalProtoJSONs[T proto.Message](protos []T) ([]byte, error) {'
assert before.count(needle)==1
candidate=before.replace(needle,needle+'''
    if len(protos)>1 {
        if values,ok:=any(protos).([]*otlpcommonv1.KeyValue);ok {
            // Encode all attributes with one encoder. The repeated field
            // keeps their normal protojson representation and order.
            encoded,err:=protojson.Marshal(&otlpcommonv1.KeyValueList{Values:values})
            if err!=nil { return nil,fmt.Errorf("failed to protojson marshal: %w",err) }
            start,end:=bytes.IndexByte(encoded,'['),bytes.LastIndexByte(encoded,']')
            if start>=0 && end>start { return encoded[start:end+1],nil }
        }
    }
''')
(root/'candidate.go').write_text(candidate)
reference=before[before.index(needle):before.index('// Attributes returns the attributes of the span')].replace('func MarshalProtoJSONs[','func beforeBulkMarshalProtoJSONs[')
(root/'reference_test.go').write_text('''package clientdb
import (
    "fmt"
    "google.golang.org/protobuf/proto"
    "google.golang.org/protobuf/encoding/protojson"
)
'''+reference)
for arm,name in [('before','before.go'),('after','candidate.go')]:
    mapping=json.loads(json.dumps(overlay))
    mapping['Replace'][logical]=str(root/name)
    mapping['Replace'][str(source/'engine/clientdb/bulk_proto_json_test.go')]=str(root/'compat_test.go')
    mapping['Replace'][str(source/'engine/clientdb/bulk_proto_json_reference_test.go')]=str(root/'reference_test.go')
    (root/(arm+'.json')).write_text(json.dumps(mapping,indent=2)+'\n')
subprocess.run(['gofmt','-w',str(root/'candidate.go'),str(root/'reference_test.go')],check=True)
print(root)
