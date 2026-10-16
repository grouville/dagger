from pathlib import Path
import json
import statistics,sys

root = Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/rust-cache-sipsma-review/containerd-root-dedup-commands')
rows = json.loads((root/'samples.json').read_text())
rows = [r for r in rows if not r['preparation']]
result = {}
for scenario in ['idle','collect']:
    selected = {arm:[r for r in rows if r['arm']==arm and r['scenario']==scenario] for arm in ['off','on']}
    pairs = {arm:{r['pair']:r for r in values} for arm,values in selected.items()}
    common = sorted(set(pairs['off']) & set(pairs['on']))
    comparison = {arm:{metric:statistics.median(r[metric] for r in values)
                       for metric in ['command_seconds','case_seconds','drain_seconds']}
                  for arm,values in selected.items()}
    for metric in ['command_seconds','case_seconds','drain_seconds']:
        savings = [pairs['off'][i][metric]-pairs['on'][i][metric] for i in common]
        comparison[metric+'_paired'] = dict(pairs=len(savings),median_saving=statistics.median(savings),faster_pairs=sum(n>0 for n in savings))
    for arm,values in selected.items():
        for row in values:
            assert not row['after_drain']['snapshot_exists']
            assert row['after_command']['snapshot_exists'] is (scenario=='idle')
        comparison[arm]['command_cpu_seconds'] = {scope:statistics.median(r['command_cpu_seconds'][scope] for r in values)
                                                 for scope in ['engine','exec','docker_total']}
        comparison[arm]['max_stall_fraction'] = {key:max(r['stall_fraction'][key] for r in values)
                                                for key in values[0]['stall_fraction']}
        if scenario=='collect':
            comparison[arm]['job_seconds'] = statistics.median(r['job']['seconds'] for r in values)
            assert all(r['job_command_overlap_seconds']>0 for r in values)
    result[scenario]=comparison
result['longest_case_seconds'] = sorted([r['case_seconds'] for r in rows],reverse=True)[:5]
result['maximum_metadata_estimated_bytes'] = max(r['after_command']['metadata_estimate']['EstimatedBytes'] for r in rows)
(root/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
