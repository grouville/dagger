from pathlib import Path
import hashlib
import json
import os
import shutil

root=Path(__file__).parent
archive=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/rust-go-test-collections')
prior=archive.parent/'span-lookup-fanout'
old=json.loads((prior/'engine/source-mirror.json').read_text())
current=root.parent/'layercopy-known-dirs'
manifest=json.loads((current/'manifest.json').read_text())
mirror={}
(root/'engine').mkdir(exist_ok=True)
for source,entry in manifest.items():
    if source in old and old[source]['sha256']==entry['sha256']:
        mirror[source]=dict(archived=os.path.relpath((prior/old[source]['archived']).resolve(),archive),sha256=entry['sha256'])
    else:
        data=Path(entry['replacement']).read_bytes();assert hashlib.sha256(data).hexdigest()==entry['sha256']
        name='engine/source-mirror/'+entry['sha256']+'.go';path=root/name;path.parent.mkdir(exist_ok=True)
        path.write_bytes(data);mirror[source]=dict(archived=name+('.gz' if len(data)>10000 else ''),sha256=entry['sha256'])
(root/'engine/source-mirror.json').write_text(json.dumps(mirror,indent=2)+'\n')
for filename in ['identity.json','manifest.json','engine-overlay.json','selected-runtime-state.json']:
    shutil.copyfile(current/filename,root/'engine'/filename)
print('Prepared engine mirror:',len(mirror),'entries')
