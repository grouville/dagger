package clientdb

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func BenchmarkSpillFileOpenAppendClose(b *testing.B) {
	path := filepath.Join(b.TempDir(), "metrics.log")
	spill, err := openSpillFile(b.Context(), path, metricCodec, nil)
	require.NoError(b, err)
	require.NoError(b, spill.close())
	rows := []Metric{{ID: 1, Data: []byte("metric")}}
	b.ReportAllocs()
	b.ResetTimer()
	for b.Loop() {
		// Reset the existing file to its header so each iteration writes ID 1.
		if err := os.Truncate(path, 1); err != nil {
			b.Fatal(err)
		}
		spill, err := openSpillFile(b.Context(), path, metricCodec, nil)
		if err != nil {
			b.Fatal(err)
		}
		if err := spill.append(rows); err != nil {
			b.Fatal(err)
		}
		if err := spill.close(); err != nil {
			b.Fatal(err)
		}
	}
}
