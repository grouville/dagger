package dagql

import (
	"context"
	"fmt"
	"testing"
)

func BenchmarkUsageProviderSampling(b *testing.B) {
	for _, count := range []int{128, 2048} {
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			ctx := cacheTestSessionContext(b.Context(), "provider-control")
			c, err := NewCache(ctx, "", nil, nil)
			if err != nil { b.Fatal(err) }
			ctx = ContextWithCache(ctx, c)
			b.Cleanup(func() { if err := c.CloseDiscardingPersistence(); err != nil { b.Error(err) } })
			for i := range count {
				frame := cacheTestIntCall(fmt.Sprintf("provider-control-%d", i))
				value := &usageCallbackValue{Int: NewInt(i), callback: func(string) {}}
				_, err := c.GetOrInitCall(ctx, "provider-control", noopTypeResolver{}, &CallRequest{ResultCall: frame}, func(context.Context) (AnyResult, error) {
					return cacheTestDetachedResult(frame, value), nil
				})
				if err != nil { b.Fatal(err) }
			}
			b.ReportAllocs()
			b.ResetTimer()
			for range b.N {
				snapshot, err := c.collectUsageMeasurementInputs(ctx, false)
				if err != nil { b.Fatal(err) }
				if len(snapshot.inputs) != count { b.Fatalf("sampled %d/%d providers", len(snapshot.inputs), count) }
				if err := snapshot.close(ctx); err != nil { b.Fatal(err) }
			}
		})
	}
}
