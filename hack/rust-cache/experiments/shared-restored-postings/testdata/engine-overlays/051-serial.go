package contenthash

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"

	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/patternmatcher"
	digest "github.com/opencontainers/go-digest"
)

// TreeFingerprint hashes paths, permissions, ownership, xattrs and file contents
// in an immutable tree. File sizes and timestamps are excluded; ignoreContents
// additionally excludes regular file contents matching those patterns.
// A rejected path, symlink or special file returns an empty digest, so callers
// can fall back to discovering inputs with their toolchain.
func treeFingerprintSerial(ctx context.Context, root string, ignoreContents, reject []string) (digest.Digest, error) {
	ignored, err := patternmatcher.New(ignoreContents)
	if err != nil {
		return "", err
	}
	rejected, err := patternmatcher.New(reject)
	if err != nil {
		return "", err
	}
	h := digest.Canonical.Digester()
	_, _ = io.WriteString(h.Hash(), "dagger.tree-fingerprint.v1\x00")
	unsupported := errors.New("unsupported fingerprint input")
	var copyBuffer []byte
	err = filepath.WalkDir(root, func(filename string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		rel, err := filepath.Rel(root, filename)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if match, err := rejected.MatchesOrParentMatches(rel); err != nil {
			return err
		} else if match {
			return unsupported
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.IsDir() && !info.Mode().IsRegular() {
			return unsupported
		}
		stat := &fstypes.Stat{Mode: uint32(info.Mode())}
		if err := setUnixOpt(filename, info, stat); err != nil {
			return err
		}
		entryHash, err := NewFromStat(stat)
		if err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			ignore, err := ignored.MatchesOrParentMatches(rel)
			if err != nil {
				return err
			}
			if !ignore {
				file, err := os.Open(filename)
				if err != nil {
					return err
				}
				if copyBuffer == nil {
					copyBuffer = make([]byte, 32<<10)
				}
				// Hide File.WriteTo so every file uses the same copy buffer.
				_, copyErr := io.CopyBuffer(entryHash, struct{ io.Reader }{file}, copyBuffer)
				if err := errors.Join(copyErr, file.Close()); err != nil {
					return err
				}
			}
		}
		_, _ = io.WriteString(h.Hash(), rel)
		_, _ = h.Hash().Write([]byte{0})
		_, _ = h.Hash().Write(entryHash.Sum(nil))
		return nil
	})
	if errors.Is(err, unsupported) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return h.Digest(), nil
}
