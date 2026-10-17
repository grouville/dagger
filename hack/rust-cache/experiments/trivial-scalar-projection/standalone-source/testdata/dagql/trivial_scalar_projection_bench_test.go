package dagql

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func BenchmarkTrivialScalarProjection(b *testing.B) {
	for _, count := range []int{1, 1026} {
		for _, fresh := range []bool{false, true} {
			b.Run(fmt.Sprintf("%d/fresh=%t", count, fresh), func(b *testing.B) {
				ctx, srv, _ := scalarProjectionFixture(b, count)
				query := `query($g:Int!){records(generation:$g){name count ratio enabled note}}`
				generation := 0
				_, err := srv.Query(ctx, query, map[string]any{"g": generation})
				require.NoError(b, err)
				b.ReportAllocs()
				for b.Loop() {
					if fresh {
						generation++
					}
					result, err := srv.Query(ctx, query, map[string]any{"g": generation})
					require.NoError(b, err)
					require.Len(b, result["records"], count)
				}
			})
		}
	}
}
