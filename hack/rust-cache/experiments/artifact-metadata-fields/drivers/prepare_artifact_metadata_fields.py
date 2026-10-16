from pathlib import Path
import json,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'artifact-metadata-fields';root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds');previous=base/'parallel-fingerprint-engine';overlay=json.loads((previous/'overlay.json').read_text())
logical=str(source/'core/schema/artifacts.go');before=Path(overlay['Replace'][logical]).read_text()
after=before
for name,method in [('description','description'),('uri','artifactURI')]:
    needle=f'dagql.Func("{name}", s.{method})';assert after.count(needle)==1
    after=after.replace(needle,needle+'.DoNotCache("simple field selection")')
(root/'before.go').write_text(before);(root/'after.go').write_text(after)
overlay['Replace'][logical]=str(root/'after.go')
overlay['Replace'][str(source/'core/schema/artifact_metadata_fields_test.go')]=str(root/'fixture_test.go')
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',str(root/'after.go')],check=True)
print(root)
