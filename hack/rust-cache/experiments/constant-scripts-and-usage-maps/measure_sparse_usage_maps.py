from pathlib import Path
import json
import os
import re
import statistics
import subprocess

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'sparse-usage-maps-bench'
root.mkdir(exist_ok=True)
rows=[]
for pair in range(5):
    row={}
    for variant in (['before','after'] if pair%2==0 else ['after','before']):
        command=[str(base/f'sparse-usage-{variant}.test'),'-test.run=^$',
                 '-test.bench=^BenchmarkCachePruneSnapshot/disk/200000$',
                 '-test.benchtime=1x','-test.count=1','-test.benchmem']
        log=root/f'{pair}-{variant}.log'
        if not log.exists():
            with log.open('w') as output:
                process=subprocess.run(command,env=dict(os.environ,GOMAXPROCS='8'),stdout=output,stderr=subprocess.STDOUT)
            assert process.returncode==0,(pair,variant)
        output=log.read_text()
        assert '\nPASS' in output,(pair,variant,output[-1000:])
        line=next(line for line in output.splitlines() if line.startswith('BenchmarkCachePruneSnapshot/disk/200000-8'))
        values=[int(re.search(r'(\d+) '+unit,line).group(1)) for unit in ['ns/op','B/op','allocs/op']]
        row[variant]=dict(zip(['ns_per_op','bytes_per_op','allocations_per_op'],values))
        print(pair,variant,row[variant],flush=True)
    rows.append(row)
    (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
summary=dict(fresh_process_per_observation=True,fixture='existing BenchmarkCachePruneSnapshot/disk/200000',
             pairs=len(rows),medians={v:{k:statistics.median(r[v][k] for r in rows) for k in rows[0][v]} for v in ['before','after']},
             median_paired_saving={k:statistics.median(r['before'][k]-r['after'][k] for r in rows) for k in rows[0]['before']},
             faster_pairs=sum(r['after']['ns_per_op']<r['before']['ns_per_op'] for r in rows),
             rust_command_gain_claimed=False)
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
