#!/usr/bin/env python3
"""Keep only fixed-label barrier counts from the separately reviewed SDK reducer."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=HERE/'clone-flush-numeric.json';raw=json.loads(source.read_text())
labels={'dang.flushTelemetry','telemetry.flushTraces','telemetry.flushLogs','telemetry.flushMetrics','telemetry.flushClientMetrics'}
result={'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sdk_reducer_sha256':raw['reducer_sha256'],'admission_reducer_sha256':raw['admission_reducer_sha256'],'profiles':[],'interpretation':'Separate profiled observations only. Actual provider calls prove all-client metric fanout occurs, but metrics aggregate union is2.49/3.22ms, not the47.53/44.09ms whole Dang barrier. Overlap prevents summing phases as removable critical-path time. No metric-only runtime candidate was tested.'}
for p in raw['profiles']:
 f=p['flush'];assert p['open_operations']==p['dropped_events']==0
 assert all(r['class']in labels for r in f['fixed_classes'])
 result['profiles'].append({'variant':p['variant'],'profile_sha256':p['profile_sha256'],'operations':p['operations'],'open_operations':p['open_operations'],'dropped_events':p['dropped_events'],'fixed_classes':f['fixed_classes'],'actual_provider_forceflush_calls_in_dang_barriers':f['actual_provider_forceflush_calls_in_dang_barriers'],'metrics_aggregate_calls_in_dang_barriers':f['metrics_aggregate_calls_in_dang_barriers'],'provider_calls_per_barrier':f['provider_calls_per_barrier'],'provider_calls_outside_dang_barriers':f['provider_calls_outside_dang_barriers']})
(HERE/'safe-evidence-v1/flush-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
