from pathlib import Path
import json

root=Path(__file__).parent/'constant-script-state'
summary=json.loads((root/'summary.json').read_text())
for variant in ['before','after']:
    import gzip
    log=root/(variant+'.log')
    text=log.read_text() if log.exists() else gzip.decompress(log.with_suffix('.log.gz').read_bytes()).decode()
    encoded=next(json.loads(line) for line in text.splitlines() if line.startswith('"['))
    _,collection=json.loads(encoded)
    start=collection.index('"project":')+len('"project":')
    _,end=json.JSONDecoder().raw_decode(collection[start:])
    raw=collection[start:start+end]
    summary[variant]['runtime_json_bytes']=len(raw.encode())
    summary[variant]['bytes_metric']='normalized compact JSON; runtime_json_bytes preserves the runtime encoder escaping'
    (root/(variant+'-runtime-project.json')).write_text(raw+'\n')
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
