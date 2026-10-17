from pathlib import Path
import subprocess
root=Path(__file__).parent
work=Path('/tmp/dagger-cache-usage-sampler-only')
(root/'read-once-cache_usage.go').write_bytes((work/'dagql/cache_usage.go').read_bytes())
(root/'read-once.patch').write_bytes(subprocess.check_output(['git','diff','ff0b029a4d270a651b9a8c7286babc79089066e4','--','dagql/cache_usage.go'],cwd=work))
source=(root/'before-cache_usage.go').read_text()
anchor='\tstate := res.loadPayloadState()\n'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'''	// Values without disk usage need no measurement ownership. Keep old sizes
	// so publication can clear them, and recheck omitted rows at finalization.
	if len(res.cacheUsageSizeByIdentity) == 0 {
		if state.hasValue && state.self != nil {
			if _, provider := state.self.(hasCacheUsageIdentity); !provider {
				return cacheUsageMeasurementInput{}
			}
		} else if len(state.snapshotOwnerLinks) == 0 {
			return cacheUsageMeasurementInput{}
		}
	}
''',1)
anchor='''		if _, held := snapshot.holds[res]; !held {
'''
assert source.count(anchor)==1
source=source.replace(anchor,'''		input := cacheUsageInputLocked(res)
		if input.row == nil {
			continue
		}
'''+anchor,1)
anchor='''		input := cacheUsageInputLocked(res)
		if input.identitiesWithoutCallbacks()'''
assert source.count(anchor)==1
source=source.replace(anchor,'\t\tif input.identitiesWithoutCallbacks()',1)
source=source.replace('identities := make(map[sharedResultID][]string, len(snapshot.cache.resultsByID))','identities := make(map[sharedResultID][]string, len(snapshot.inputs))',1)
anchor='\t\t\tinput = cacheUsageInputLocked(res)\n'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'''			if input.row == nil {
				continue
			}
''',1)
(work/'dagql/cache_usage.go').write_text(source)
(root/'minimal-cache_usage.go').write_text(source)
(root/'minimal.patch').write_bytes(subprocess.check_output(['git','diff','ff0b029a4d270a651b9a8c7286babc79089066e4','--','dagql/cache_usage.go'],cwd=work))
print('Prepared minimal sampler: retain existing sampled-provider validation path; classify only new or changed inputs.')
