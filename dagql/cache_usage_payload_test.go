package dagql

import "testing"

func TestCacheUsageInputOwnsSnapshotLinks(t *testing.T) {
	row := &sharedResult{
		id: 1, payloadRevision: 3,
		snapshotOwnerLinks: []PersistedSnapshotRefLink{{
			Role: "snapshot", RefKey: "original",
			OutputPath: PersistedRefPath{}.Field("items").Index(0),
		}},
		cacheUsageSizeByIdentity: map[string]int64{"original": 64},
	}
	c := &Cache{resultsByID: map[sharedResultID]*sharedResult{row.id: row}}
	c.egraphMu.Lock()
	defer c.egraphMu.Unlock()
	input := cacheUsageInputLocked(row)
	if !input.validLocked(c) {
		t.Fatal("a new sample must match its row")
	}
	row.payloadMu.Lock()
	row.snapshotOwnerLinks[0].RefKey = "replacement"
	row.snapshotOwnerLinks[0].OutputPath[1].Index = 1
	row.payloadRevision++
	row.payloadMu.Unlock()
	row.cacheUsageSizeByIdentity["original"] = 128
	if input.snapshotLinks[0].RefKey != "original" || input.snapshotLinks[0].OutputPath[1].Index != 0 || input.existingSizeByID["original"] != 64 {
		t.Fatal("changing a row changed its captured usage sample")
	}
	if input.validLocked(c) {
		t.Fatal("a sample must be invalid after payload replacement")
	}
}

func BenchmarkCacheUsagePayload(b *testing.B) {
	for _, kind := range []string{"scalar", "loaded", "unloaded"} {
		b.Run(kind, func(b *testing.B) {
			row := &sharedResult{id: 1, payloadRevision: 3}
			if kind != "unloaded" {
				row.self, row.hasValue = NewInt(1), true
			}
			if kind != "scalar" {
				for i := range 4 {
					row.snapshotOwnerLinks = append(row.snapshotOwnerLinks, PersistedSnapshotRefLink{
						Role: "snapshot", RefKey: "snapshot",
						OutputPath: PersistedRefPath{}.Field("items").Index(i),
					})
				}
				row.cacheUsageSizeByIdentity = map[string]int64{"snapshot": 64}
			}
			c := &Cache{resultsByID: map[sharedResultID]*sharedResult{row.id: row}}
			c.egraphMu.Lock()
			defer c.egraphMu.Unlock()
			b.Run("capture", func(b *testing.B) {
				b.ReportAllocs()
				var input cacheUsageMeasurementInput
				for b.Loop() {
					input = cacheUsageInputLocked(row)
				}
				if input.row != row {
					b.Fatal("lost row")
				}
			})
			b.Run("validate", func(b *testing.B) {
				input := cacheUsageInputLocked(row)
				b.ReportAllocs()
				for b.Loop() {
					if !input.validLocked(c) {
						b.Fatal("sample changed")
					}
				}
			})
		})
	}
}
