package workspace

import (
	"fmt"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestParseConfigAtChecksFieldsAfterDecode(t *testing.T) {
	t.Run("unconsumed alias keeps its position", func(t *testing.T) {
		_, err := ParseConfigAt(t.Context(), []byte("[modules.provider]\nsource = './sdk'\nSOURCE = './ignored'\n"), "nested")
		require.EqualError(t, err, "nested/dagger.toml:3:1: unknown field modules.provider.SOURCE")
	})
	t.Run("arbitrary settings remain unrestricted", func(t *testing.T) {
		cfg, err := ParseConfigAt(t.Context(), []byte("[modules.provider]\nSOURCE = './sdk'\n[modules.provider.settings]\nanything = { nested = [1, 2] }\n"), ".")
		require.NoError(t, err)
		require.Equal(t, "./sdk", cfg.Modules["provider"].Source)
		require.Equal(t, map[string]any{"nested": []any{int64(1), int64(2)}}, cfg.Modules["provider"].Settings["anything"])
	})
}

func BenchmarkParseConfigAt(b *testing.B) {
	for _, scopes := range []int{0, 32, 256} {
		b.Run(fmt.Sprint(scopes), func(b *testing.B) {
			var text strings.Builder
			text.WriteString("[modules.go]\nsource = './sdk'\n[modules.go.settings]\nversion = '1.26.6'\n")
			if scopes > 0 {
				text.WriteString("[sdks.go]\nmodule = 'go'\n")
			}
			for i := range scopes {
				fmt.Fprintf(&text, "[sdks.go.scopes.'packages/%04d']\nis-module = true\nclients = ['github.com/acme/client']\n", i)
			}
			data := []byte(text.String())
			b.ReportAllocs()
			b.SetBytes(int64(len(data)))
			b.ResetTimer()
			for b.Loop() {
				cfg, err := ParseConfigAt(b.Context(), data, ".")
				if err != nil {
					b.Fatal(err)
				}
				if cfg.Modules["go"].Source != "./sdk" {
					b.Fatal("configuration changed")
				}
			}
		})
	}
}
