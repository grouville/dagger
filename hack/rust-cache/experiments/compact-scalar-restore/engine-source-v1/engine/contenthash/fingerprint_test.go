package contenthash

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"gotest.tools/v3/assert"
)

func TestTreeFingerprintDiscoveryInputs(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*testing.T, string)
		same   bool
	}{
		{"Rust contents and size", func(t *testing.T, root string) {
			writeFile(t, root, "member/src/lib.rs", "different Rust contents and length")
		}, true},
		{"timestamps", func(t *testing.T, root string) {
			assert.NilError(t, os.Chtimes(filepath.Join(root, "Cargo.toml"), time.Unix(1, 0), time.Unix(1, 0)))
		}, true},
		{"manifest contents", func(t *testing.T, root string) {
			writeFile(t, root, "Cargo.toml", "changed manifest")
		}, false},
		{"new Rust target", func(t *testing.T, root string) {
			writeFile(t, root, "member/src/main.rs", "fn main() {}")
		}, false},
		{"removed Rust target", func(t *testing.T, root string) {
			assert.NilError(t, os.Remove(filepath.Join(root, "member/src/lib.rs")))
		}, false},
		{"renamed directory", func(t *testing.T, root string) {
			assert.NilError(t, os.Rename(filepath.Join(root, "member"), filepath.Join(root, "renamed")))
		}, false},
		{"Rust permissions", func(t *testing.T, root string) {
			assert.NilError(t, os.Chmod(filepath.Join(root, "member/src/lib.rs"), 0o600))
		}, false},
		{"directory permissions", func(t *testing.T, root string) {
			assert.NilError(t, os.Chmod(filepath.Join(root, "member/src"), 0o700))
		}, false},
		{"root permissions", func(t *testing.T, root string) {
			assert.NilError(t, os.Chmod(root, 0o750))
		}, false},
		{"empty directory", func(t *testing.T, root string) {
			assert.NilError(t, os.Mkdir(filepath.Join(root, "empty"), 0o755))
		}, false},
		{"file kind", func(t *testing.T, root string) {
			assert.NilError(t, os.Remove(filepath.Join(root, "member/src/lib.rs")))
			assert.NilError(t, os.Mkdir(filepath.Join(root, "member/src/lib.rs"), 0o644))
		}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			writeFile(t, root, "Cargo.toml", "manifest")
			writeFile(t, root, "member/src/lib.rs", "before")
			assert.NilError(t, os.Chmod(filepath.Join(root, "member/src/lib.rs"), 0o644))
			fingerprint := func() string {
				t.Helper()
				dgst, err := TreeFingerprint(t.Context(), root, []string{"**/*.rs"}, []string{"**/.cargo"})
				assert.NilError(t, err)
				assert.Assert(t, dgst != "")
				return dgst.String()
			}
			before := fingerprint()
			tc.change(t, root)
			assert.Equal(t, before == fingerprint(), tc.same)
		})
	}
}

func TestTreeFingerprintUnsupportedInputs(t *testing.T) {
	for _, name := range []string{"lib.rs", "Cargo.toml", "broken", ".cargo", "nested/.cargo"} {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			writeFile(t, root, "manifest.rs", "manifest contents")
			assert.NilError(t, os.MkdirAll(filepath.Dir(filepath.Join(root, name)), 0o755))
			target := "manifest.rs"
			if name == "broken" {
				target = "/does/not/exist"
			}
			assert.NilError(t, os.Symlink(target, filepath.Join(root, name)))
			dgst, err := TreeFingerprint(t.Context(), root, []string{"**/*.rs"}, []string{"**/.cargo"})
			assert.NilError(t, err)
			assert.Equal(t, dgst.String(), "")
		})
	}
	root := t.TempDir()
	assert.NilError(t, os.MkdirAll(filepath.Join(root, "member/.cargo"), 0o755))
	dgst, err := TreeFingerprint(t.Context(), root, nil, []string{"**/.cargo"})
	assert.NilError(t, err)
	assert.Equal(t, dgst.String(), "")
	_, err = TreeFingerprint(t.Context(), root, []string{"["}, nil)
	assert.Assert(t, err != nil, "invalid patterns must fail")
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err = TreeFingerprint(ctx, root, nil, nil)
	assert.Assert(t, errors.Is(err, context.Canceled))
}

func TestTreeFingerprintCanonicalOrder(t *testing.T) {
	a, b := t.TempDir(), t.TempDir()
	for _, root := range []string{a, b} {
		assert.NilError(t, os.Chmod(root, 0o755))
	}
	writeFile(t, a, "a.rs", "before")
	writeFile(t, a, "Cargo.toml", "manifest")
	writeFile(t, b, "Cargo.toml", "manifest")
	writeFile(t, b, "a.rs", "after, different size")
	x, err := TreeFingerprint(t.Context(), a, []string{"**/*.rs"}, nil)
	assert.NilError(t, err)
	y, err := TreeFingerprint(t.Context(), b, []string{"**/*.rs"}, nil)
	assert.NilError(t, err)
	assert.Equal(t, x, y, "creation order must not matter")
}

func BenchmarkTreeFingerprintWorkspace(b *testing.B) {
	root := b.TempDir()
	for i := range 128 {
		dir := filepath.Join(root, fmt.Sprintf("crate-%03d", i))
		if err := os.MkdirAll(filepath.Join(dir, "src"), 0o755); err != nil {
			b.Fatal(err)
		}
		for _, name := range []string{"Cargo.toml", "src/lib.rs"} {
			if err := os.WriteFile(filepath.Join(dir, name), []byte("fixture contents"), 0o644); err != nil {
				b.Fatal(err)
			}
		}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for b.Loop() {
		if _, err := TreeFingerprint(b.Context(), root, []string{"**/*.rs"}, []string{"**/.cargo"}); err != nil {
			b.Fatal(err)
		}
	}
}
