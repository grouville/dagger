package dagql

import (
	"context"
	"io"
	"runtime"
	"strconv"
	"testing"
)

func BenchmarkCachePruneProviderDense(b *testing.B) {
	const count = 200000
	b.ReportAllocs()
	for range b.N {
		b.StopTimer()
		ctx := benchmarkMetadataContext(b, io.Discard)
		c, err := NewCache(ctx, "", nil, nil)
		if err != nil {
			b.Fatal(err)
		}
		identities := []string{"provider-dense-shared"}
		sizes := map[string]int64{"provider-dense-shared": 64}
		for i := range count {
			frame := cacheTestIntCall("provider-dense-" + strconv.Itoa(i))
			value := cacheTestSizedInt{Int: NewInt(i), usageIdentities: identities, sizeByIdentity: sizes}
			_, err := c.GetOrInitCall(ctx, "provider-dense", noopTypeResolver{}, &CallRequest{ResultCall: frame, IsPersistable: true}, func(context.Context) (AnyResult, error) {
				return cacheTestDetachedResult(frame, value), nil
			})
			if err != nil {
				b.Fatal(err)
			}
		}
		if err := c.ReleaseSession(ctx, "provider-dense"); err != nil {
			b.Fatal(err)
		}
		if err := c.measureAllResultSizes(ctx); err != nil {
			b.Fatal(err)
		}
		b.StartTimer()
		snapshot := c.snapshotPruneState(pruneSnapshotDisk, 0)
		b.StopTimer()
		if len(snapshot.results) != count || snapshot.usedBytes != 64 {
			b.Fatalf("rows=%d bytes=%d", len(snapshot.results), snapshot.usedBytes)
		}
		b.ReportMetric(float64(len(snapshot.results)), "snapshot-results")
		runtime.KeepAlive(c)
		runtime.KeepAlive(ctx)
	}
}
