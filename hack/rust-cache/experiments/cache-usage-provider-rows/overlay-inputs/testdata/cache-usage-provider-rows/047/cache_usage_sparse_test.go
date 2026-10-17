package dagql

import (
	"context"
	"errors"
	"io"
	"runtime"
	"strconv"
	"testing"
)

func TestCacheUsageRechecksEmptyPayloadAtFinalization(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	c, err := NewCache(ctx, "", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := c.Close(context.Background()); err != nil {
			t.Error(err)
		}
	})
	row := publishProgressValue(t, ctx, c, "holder", "empty", NewInt(1), false).cacheSharedResult()
	snapshot, err := c.collectUsageMeasurementInputs(ctx, false)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := snapshot.close(ctx); err != nil {
			t.Error(err)
		}
	}()

	c.egraphMu.Lock()
	row.payloadMu.Lock()
	row.self = &usageCallbackValue{Int: NewInt(2), callback: func(string) {
		t.Error("unsampled provider called during finalization")
	}}
	row.payloadRevision++
	row.payloadMu.Unlock()
	_, err = snapshot.finalizeLocked()
	c.egraphMu.Unlock()
	if !errors.Is(err, errCacheUsageChanged) {
		t.Fatalf("new provider was accepted without sampling: %v", err)
	}
}

func TestCacheUsageClearsMeasurementsAfterPayloadBecomesEmpty(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	c, err := NewCache(ctx, "", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := c.Close(context.Background()); err != nil {
			t.Error(err)
		}
	})
	row := publishUsageValue(t, c, "provider", &usageCallbackValue{
		Int: NewInt(1), callback: func(string) {},
	}).cacheSharedResult()
	if err := c.measureAllResultSizes(ctx); err != nil {
		t.Fatal(err)
	}
	if row.cacheUsageSizeByIdentity["shared-snapshot"] != 64 {
		t.Fatalf("fixture has no measured usage: %v", row.cacheUsageSizeByIdentity)
	}
	c.egraphMu.Lock()
	row.payloadMu.Lock()
	row.self = NewInt(2)
	row.payloadRevision++
	row.payloadMu.Unlock()
	c.egraphMu.Unlock()
	if err := c.measureAllResultSizes(ctx); err != nil {
		t.Fatal(err)
	}
	if len(row.cacheUsageSizeByIdentity) != 0 {
		t.Fatalf("empty payload retained old measurements: %v", row.cacheUsageSizeByIdentity)
	}
}

func BenchmarkCachePruneWithoutReclaimTarget(b *testing.B) {
	for _, count := range []int{200_000, 1_000_000} {
		b.Run(strconv.Itoa(count), func(b *testing.B) {
			b.ReportAllocs()
			for range b.N {
				b.StopTimer()
				c, ctx, _ := benchmarkMetadataPruneCache(b, count, benchmarkMetadataMinimal, "", io.Discard)
				const providers = 16
				for i := range providers {
					name := "usage-provider-" + strconv.Itoa(i)
					frame := cacheTestIntCall(name)
					value := cacheTestSizedInt{Int: NewInt(i), usageIdentities: []string{name}, sizeByIdentity: map[string]int64{name: 1024}}
					_, err := c.GetOrInitCall(ctx, "usage-providers", noopTypeResolver{}, &CallRequest{
						ResultCall: frame, IsPersistable: true,
					}, func(context.Context) (AnyResult, error) {
						return cacheTestDetachedResult(frame, value), nil
					})
					if err != nil {
						b.Fatal(err)
					}
				}
				if err := c.ReleaseSession(ctx, "usage-providers"); err != nil {
					b.Fatal(err)
				}
				b.StartTimer()
				report, err := c.Prune(ctx, []CachePrunePolicy{{All: true, MaxUsedSpace: 1 << 40}})
				b.StopTimer()
				if err != nil || len(report.Entries) != 0 || c.Size() != count+providers {
					b.Fatalf("no-target prune: error=%v, removed=%d, retained=%d", err, len(report.Entries), c.Size())
				}
				b.ReportMetric(float64(c.Size()), "retained-results")
				runtime.KeepAlive(c)
				runtime.KeepAlive(ctx)
			}
		})
	}
}
