package fsutil
import ("fmt"; gofs "io/fs"; "os"; "path/filepath"; "testing"; "github.com/stretchr/testify/require")
func BenchmarkFilterFSWildcardControl(b *testing.B) {
	for _, width := range []int{128} {
		root := b.TempDir()
		require.NoError(b, os.MkdirAll(filepath.Join(root, "a/b/selected"), 0o750))
		require.NoError(b, os.WriteFile(filepath.Join(root, "a/b/selected/child"), nil, 0o600))
		for i := range width {
			require.NoError(b, os.Mkdir(filepath.Join(root, fmt.Sprintf("sibling%04d", i)), 0o750))
		}
		b.Run(fmt.Sprint(width), func(b *testing.B) {
			base, err := NewFS(root)
			require.NoError(b, err)
			for b.Loop() {
				filtered, err := NewFilterFS(base, &FilterOpt{IncludePatterns: []string{"a/b/selecte[d]"}, ExcludePatterns: []string{"a/b/selected/*"}})
				require.NoError(b, err)
				count := 0
				err = filtered.Walk(b.Context(), "", func(_ string, _ gofs.DirEntry, err error) error { count++; return err })
				require.NoError(b, err)
				require.Equal(b, 3, count)
			}
		})
	}
}
