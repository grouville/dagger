package clientdb

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func BenchmarkSpillFileRecover(b *testing.B) {
	for _, count := range []int{0, 1, 512} {
		b.Run(fmt.Sprintf("rows=%d", count), func(b *testing.B) {
			path := filepath.Join(b.TempDir(), "metrics.log")
			spill, err := openSpillFile(b.Context(), path, metricCodec, nil)
			require.NoError(b, err)
			rows := make([]Metric, count)
			for i := range rows {
				rows[i] = Metric{ID: int64(i + 1), Data: []byte("recovered metric")}
			}
			require.NoError(b, spill.append(rows))
			require.NoError(b, spill.close())
			file, err := os.Open(path)
			require.NoError(b, err)
			b.Cleanup(func() { require.NoError(b, file.Close()) })
			info, err := file.Stat()
			require.NoError(b, err)
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				recovered := spillFile[Metric]{file: file, codec: metricCodec}
				if err := recovered.recover(b.Context(), info.Size(), nil); err != nil {
					b.Fatal(err)
				}
				if recovered.rowCount != int64(count) {
					b.Fatalf("recovered %d rows, want %d", recovered.rowCount, count)
				}
			}
		})
	}
}
