package clientdb

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSpillFileEmptyReopenThenAppend(t *testing.T) {
	path := filepath.Join(t.TempDir(), "metrics.log")
	spill, err := openSpillFile(t.Context(), path, metricCodec, nil)
	require.NoError(t, err)
	require.NoError(t, spill.append(nil))
	rows, err := spill.readSince(t.Context(), 0, 1)
	require.NoError(t, err)
	require.Empty(t, rows)
	require.NoError(t, spill.close())

	spill, err = openSpillFile(t.Context(), path, metricCodec, nil)
	require.NoError(t, err)
	want := []Metric{{ID: 1, Data: []byte("first row")}}
	require.NoError(t, spill.append(want))
	require.NoError(t, spill.close())

	var recovered []Metric
	spill, err = openSpillFile(t.Context(), path, metricCodec, func(row Metric) {
		recovered = append(recovered, row)
	})
	require.NoError(t, err)
	require.Equal(t, want, recovered)
	require.NoError(t, spill.close())
}

func BenchmarkSpillFileOpenClose(b *testing.B) {
	for _, count := range []int{0, 1, 256} {
		name := "empty"
		if count > 0 {
			name = "one-row"
		}
		if count > 1 {
			name = "256-rows"
		}
		b.Run(name, func(b *testing.B) {
			path := filepath.Join(b.TempDir(), "metrics.log")
			spill, err := openSpillFile(b.Context(), path, metricCodec, nil)
			require.NoError(b, err)
			rows := make([]Metric, count)
			for i := range rows {
				rows[i] = Metric{ID: int64(i + 1), Data: []byte("metric")}
			}
			require.NoError(b, spill.append(rows))
			require.NoError(b, spill.close())
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				spill, err := openSpillFile(b.Context(), path, metricCodec, nil)
				if err != nil {
					b.Fatal(err)
				}
				if err := spill.close(); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
