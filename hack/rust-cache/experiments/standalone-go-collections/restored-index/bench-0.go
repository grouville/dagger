package dagql
import ("fmt"; "testing"; "gotest.tools/v3/assert")
func BenchmarkCacheImportWideOutputClass(b *testing.B) {
	for _, width := range []int{64, 256, 1024} {
		b.Run(fmt.Sprint(width), func(b *testing.B) {
			f := cacheDerivedIndexWideOutputFixture(b, width, true)
			assert.NilError(b, f.cache.Close(b.Context()))
			f.cache = nil
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				c, err := NewCache(f.ctx, f.dbPath, nil, nil)
				assert.NilError(b, err)
				b.StopTimer()
				assert.Equal(b, CachePersistenceResetNone, c.PersistenceResetReason())
				assert.Equal(b, 2*width+1, len(c.resultsByID))
				assert.NilError(b, c.Close(b.Context()))
				b.StartTimer()
			}
		})
	}
}
