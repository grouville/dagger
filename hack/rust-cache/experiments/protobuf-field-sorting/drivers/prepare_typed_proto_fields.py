from pathlib import Path
import hashlib,json,shutil,subprocess

base=Path('/tmp/rust-cache-sipsma-review');old=base/'small-proto-fields';root=base/'typed-proto-fields';root.mkdir(exist_ok=False)
protobuf=Path('/tmp/protobuf-field-order-experiment');source=Path('/tmp/dagger-filesync-snapshot-seeds')
candidate=(old/'field-sorter-screen/candidate.go').read_text()
(root/'candidate.go').write_text(candidate);shutil.copyfile(old/'before.go',root/'before.go')
start=candidate.index('\tswitch len(fields) {');end=candidate.index('\n\t// Visit the fields in the specified ordering.',start)
fast=candidate[start:end]
controlled=candidate[:start]+'''\tif smallFields.Load() {
'''+fast+'''
    } else {
        sort.Slice(fields, func(i,j int) bool { return less(fields[i].fd,fields[j].fd) })
    }
'''+candidate[end:]
(root/'controlled.go').write_text(controlled)
overlay=json.loads((old/'overlay.json').read_text())
for logical,item in json.loads((old/'manifest.json').read_text()).items():assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],logical
overlay['Replace'][str(protobuf/'internal/order/range.go')]=str(root/'controlled.go')
debug=(old/'debug.go').read_text().replace('/debug/small-proto-fields','/debug/typed-proto-fields');(root/'debug.go').write_text(debug)
overlay['Replace'][str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
for name in ['engine.go.mod','engine.go.sum']:shutil.copyfile(old/name,root/name)
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
for name,seed in [('measure_commands.py',2026101606),('confirm_commands.py',2026101607)]:
    text=(old/'measure_commands.py').read_text().replace('random_seed=2026101604','random_seed='+str(seed)).replace("base/'small-proto-fields/identity.json'","base/'typed-proto-fields/identity.json'").replace("mode('small-proto-fields'","mode('typed-proto-fields'")
    text=text.replace('Original versus zero/one/two-field Protobuf ordering on the selected native-discovery module; larger message and map sorts unchanged; balanced randomized order, all admitted observations retained.','Original versus small-message fast paths and typed sort.Interface for larger Protobuf messages; map sorting unchanged; selected native-discovery module, balanced randomized order, all admitted observations retained.')
    (root/name).write_text(text)
text=(old/'profile_commands.py').read_text().replace("base/'small-proto-fields/identity.json'","base/'typed-proto-fields/identity.json'").replace("mode('small-proto-fields'","mode('typed-proto-fields'")
(root/'profile_commands.py').write_text(text)
subprocess.run(['gofmt','-w',str(root/'candidate.go'),str(root/'controlled.go'),str(root/'debug.go')],check=True)
print(root)
