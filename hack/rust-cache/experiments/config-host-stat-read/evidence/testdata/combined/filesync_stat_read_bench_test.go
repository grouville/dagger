package engineutil

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	fsutiltypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func BenchmarkCallerHostStatRead(b *testing.B) {
	client, ctx, source := newStatReadClient(b, false)
	root := b.TempDir()
	file := filepath.Join(root, "dagger.toml")
	body := strings.Repeat("configuration\n", 120)
	require.NoError(b, os.WriteFile(file, []byte(body), 0o600))
	for _, scenario := range []struct {
		name, path, data string
		stat, dir        bool
		code             codes.Code
	}{
		{"regular", file, body, true, false, codes.OK},
		{"missing", filepath.Join(root, "missing"), "", false, false, codes.NotFound},
		{"directory", root, "", true, true, codes.OK},
	} {
		for _, combined := range []bool{false, true} {
			mode := "separate"
			if combined {
				mode = "combined"
			}
			b.Run(scenario.name+"/"+mode, func(b *testing.B) {
				read := func() ([]byte, *fsutiltypes.Stat, error) {
					if combined {
						return client.ReadCallerHostFileWithStat(ctx, scenario.path)
					}
					stat, err := client.StatCallerHostPath(ctx, scenario.path, false)
					if err != nil {
						return nil, nil, err
					}
					if stat.IsDir() {
						return nil, stat, nil
					}
					data, err := client.ReadCallerHostFile(ctx, scenario.path)
					return data, stat, err
				}
				check := func() {
					data, stat, err := read()
					if status.Code(err) != scenario.code || string(data) != scenario.data || (stat != nil) != scenario.stat {
						b.Fatalf("data=%q, stat=%v, err=%v", data, stat, err)
					}
					if stat != nil && stat.IsDir() != scenario.dir {
						b.Fatal("wrong directory status")
					}
				}
				check()
				before := source.count()
				b.ReportAllocs()
				b.ResetTimer()
				for range b.N {
					check()
				}
				b.StopTimer()
				b.ReportMetric(float64(source.count()-before)/float64(b.N), "requests/op")
			})
		}
	}
}
