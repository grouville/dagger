package contenthash

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sync"

	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/patternmatcher"
	digest "github.com/opencontainers/go-digest"
)

// TreeFingerprint hashes paths, permissions, ownership, xattrs and file contents
// in an immutable tree. File sizes and timestamps are excluded; ignoreContents
// additionally excludes regular file contents matching those patterns.
// A rejected path, symlink or special file returns an empty digest, so callers
// can fall back to discovering inputs with their toolchain.
func treeFingerprintParallel(ctx context.Context, root string, ignoreContents, reject []string) (digest.Digest, error) {
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

	type entryWork struct {
		filename string
		rel      string
		entry    fs.DirEntry
		ignore   bool
		sum      []byte
		err      error
	}
	const batchSize = 128
	concurrency := min(8, runtime.GOMAXPROCS(0))
	jobs := make(chan *entryWork, batchSize)
	var pending sync.WaitGroup
	var workers sync.WaitGroup
	workers.Add(concurrency)
	for range concurrency {
		go func() {
			defer workers.Done()
			var copyBuffer []byte
			for job := range jobs {
				if job.err == nil {
					job.sum, job.err = fingerprintEntry(ctx, job.filename, job.entry, job.ignore, &copyBuffer, unsupported)
				}
				pending.Done()
			}
		}()
	}
	defer func() { close(jobs); workers.Wait() }()

	batch := make([]entryWork, 0, batchSize)
	flush := func() error {
		pending.Add(len(batch))
		for i := range batch {
			jobs <- &batch[i]
		}
		pending.Wait()
		// WalkDir's lexical order defines the digest and error precedence.
		for _, job := range batch {
			if job.err != nil {
				return job.err
			}
			_, _ = io.WriteString(h.Hash(), job.rel)
			_, _ = h.Hash().Write([]byte{0})
			_, _ = h.Hash().Write(job.sum)
		}
		clear(batch)
		batch = batch[:0]
		return nil
	}
	err = filepath.WalkDir(root, func(filename string, entry fs.DirEntry, walkErr error) error {
		job := entryWork{filename: filename, entry: entry, err: walkErr}
		if job.err == nil {
			job.err = ctx.Err()
		}
		if job.err == nil {
			job.rel, job.err = filepath.Rel(root, filename)
			job.rel = filepath.ToSlash(job.rel)
		}
		if job.err == nil {
			var match bool
			match, job.err = rejected.MatchesOrParentMatches(job.rel)
			if match {
				job.err = unsupported
			}
		}
		if job.err == nil {
			job.ignore, job.err = ignored.MatchesOrParentMatches(job.rel)
		}
		batch = append(batch, job)
		if len(batch) == batchSize || job.err != nil {
			return flush()
		}
		return nil
	})
	if err == nil {
		err = flush()
	}

	if errors.Is(err, unsupported) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return h.Digest(), nil
}

func fingerprintEntry(ctx context.Context, filename string, entry fs.DirEntry, ignore bool, copyBuffer *[]byte, unsupported error) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	info, err := entry.Info()
	if err != nil {
		return nil, err
	}
	if !info.IsDir() && !info.Mode().IsRegular() {
		return nil, unsupported
	}
	stat := &fstypes.Stat{Mode: uint32(info.Mode())}
	if err := setUnixOpt(filename, info, stat); err != nil {
		return nil, err
	}
	entryHash, err := NewFromStat(stat)
	if err != nil {
		return nil, err
	}
	if info.Mode().IsRegular() && !ignore {
		file, err := os.Open(filename)
		if err != nil {
			return nil, err
		}
		if *copyBuffer == nil {
			*copyBuffer = make([]byte, 32<<10)
		}
		_, copyErr := io.CopyBuffer(entryHash, struct{ io.Reader }{file}, *copyBuffer)
		if err := errors.Join(copyErr, file.Close()); err != nil {
			return nil, err
		}
	}
	return entryHash.Sum(nil), nil
}
