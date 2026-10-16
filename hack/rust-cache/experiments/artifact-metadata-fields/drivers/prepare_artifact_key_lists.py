from pathlib import Path
import json,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'artifact-key-lists';root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds')
previous=base/'parallel-fingerprint-engine';overlay=json.loads((previous/'overlay.json').read_text())
logical=str(source/'core/artifacts.go');before=Path(overlay['Replace'][logical]).read_text()
old='`field:"true" doc:"The module name, collection keys, and full path key in the artifact type dimension."`'
assert before.count(old)==1
after=before.replace(old,old[:-1]+' doNotCache:"simple field selection"`')
(root/'before.go').write_text(before);(root/'after.go').write_text(after)
overlay['Replace'][logical]=str(root/'after.go')
overlay['Replace'][str(source/'core/schema/artifact_key_lists_test.go')]=str(root/'fixture_test.go')
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',str(root/'after.go')],check=True)
print(root)
