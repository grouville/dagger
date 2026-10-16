from pathlib import Path
import hashlib,json,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'span-lookup-fanout';root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds')
before=(source/'engine/clientdb/telemetry_store.go').read_text()
after=before
old='''		kids := l.causalChildren[target]
		if !slices.Contains(kids, row.SpanID) {
			l.causalChildren[target] = append(kids, row.SpanID)
		}
		parents := l.causalParents[row.SpanID]
		if !slices.Contains(parents, target) {
			l.causalParents[row.SpanID] = append(parents, target)
		}'''
new='''		parents := l.causalParents[row.SpanID]
		if slices.Contains(parents, target) {
			continue
		}
		// Both directions are populated together. Check the linking span's
		// targets rather than every span that links to a shared target.
		l.causalParents[row.SpanID] = append(parents, target)
		l.causalChildren[target] = append(l.causalChildren[target], row.SpanID)'''
assert after.count(old)==1;after=after.replace(old,new)
old='''	if row.ParentSpanID.Valid {
		if _, known := l.parent[row.SpanID]; !known {
			l.parent[row.SpanID] = row.ParentSpanID.String
		}
	}'''
new='''	var parentKnown bool
	if row.ParentSpanID.Valid {
		_, parentKnown = l.parent[row.SpanID]
		if !parentKnown {
			l.parent[row.SpanID] = row.ParentSpanID.String
		}
	}'''
assert after.count(old)==1;after=after.replace(old,new)
old='''		// A repeated span ID in another trace is vanishingly rare, but the
		// children map follows the SQL query's span-ID-only identity and must
		// remain unique if it happens.
		for _, child := range children {
			if child == row.SpanID {
				return
			}
		}'''
new='''		// New span IDs cannot already be in a child list. Only a repeated
		// ID in another trace needs the span-ID-only uniqueness check.
		if parentKnown && slices.Contains(children, row.SpanID) {
			return
		}'''
assert after.count(old)==1;after=after.replace(old,new)
(root/'before.go').write_text(before);(root/'after.go').write_text(after)
overlay=json.loads((base/'artifact-metadata-fields/engine-overlay.json').read_text())
overlay['Replace'][str(source/'engine/clientdb/telemetry_store.go')]=str(root/'after.go')
overlay['Replace'][str(source/'engine/clientdb/span_lookup_fanout_test.go')]=str(root/'fanout_test.go')
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',str(root/'after.go')],check=True)
print('Prepared span lookup changes; no new map, lock or retained field')
