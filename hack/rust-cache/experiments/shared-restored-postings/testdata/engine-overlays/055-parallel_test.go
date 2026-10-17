package contenthash

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"golang.org/x/sys/unix"
)

func TestTreeFingerprintParallelCompatibility(t *testing.T) {
	root := t.TempDir()
	for i := range 300 {
		dir := filepath.Join(root, fmt.Sprintf("crate-%04d", i), "src")
		if err := os.MkdirAll(dir, 0o751); err != nil {
			t.Fatal(err)
		}
		for _, name := range []string{"lib.rs", "data.txt"} {
			if err := os.WriteFile(filepath.Join(dir, name), []byte(fmt.Sprint(i)), 0o640); err != nil {
				t.Fatal(err)
			}
		}
	}
	compare := func(t *testing.T) {
		t.Helper()
		for _, ignore := range [][]string{nil, {"**/*.rs"}, {"**/*.rs", "!crate-0001/src/lib.rs"}} {
			want, wantErr := treeFingerprintSerialReference(t.Context(), root, ignore, []string{"**/.cargo"})
			got, gotErr := TreeFingerprint(t.Context(), root, ignore, []string{"**/.cargo"})
			if fmt.Sprint(gotErr) != fmt.Sprint(wantErr) || got != want {
				t.Fatalf("ignore=%v: got %s / %v, want %s / %v", ignore, got, gotErr, want, wantErr)
			}
		}
	}
	t.Run("multiple batches", compare)
	t.Run("metadata and unusual paths", func(t *testing.T) {
		name := filepath.Join(root, "space\ttab\nnewline-λ.rs")
		if err := os.WriteFile(name, []byte("ignored contents"), 0o751); err != nil {
			t.Fatal(err)
		}
		if err := unix.Setxattr(name, "user.fingerprint", []byte("metadata"), 0); err != nil {
			t.Fatal(err)
		}
		compare(t)
	})
	t.Run("rejected directory", func(t *testing.T) {
		name := filepath.Join(root, "crate-0200", ".cargo")
		if err := os.Mkdir(name, 0o755); err != nil {
			t.Fatal(err)
		}
		defer os.Remove(name)
		compare(t)
	})
	t.Run("symlink", func(t *testing.T) {
		name := filepath.Join(root, "000-link")
		if err := os.Symlink("crate-0000", name); err != nil {
			t.Fatal(err)
		}
		defer os.Remove(name)
		compare(t)
	})
	t.Run("repeated cancellation", func(t *testing.T) {
		ctx, cancel := context.WithCancel(t.Context())
		cancel()
		for range 100 {
			if _, err := TreeFingerprint(ctx, root, nil, nil); err != context.Canceled {
				t.Fatalf("got %v", err)
			}
		}
	})
}
