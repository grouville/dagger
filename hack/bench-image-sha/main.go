package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"runtime"
	"runtime/debug"
	"syscall"
	"time"
)

func cpuNS() (int64, error) {
	var r syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &r); err != nil {
		return 0, err
	}
	return r.Utime.Nano() + r.Stime.Nano(), nil
}

func run() error {
	path := flag.String("input", "", "complete read-only input blob")
	expected := flag.String("sha256", "", "required full digest")
	length := flag.Int64("size", 0, "required exact bytes")
	chunk := flag.Int("chunk", 256*1024, "per-Write chunk bytes")
	flag.Parse()
	if *path == "" || len(*expected) != 64 || *length <= 0 || *chunk <= 0 || *chunk > 16*1024*1024 {
		return fmt.Errorf("missing or invalid arguments")
	}
	f, err := os.Open(*path)
	if err != nil {
		return err
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil || !before.Mode().IsRegular() || before.Size() != *length {
		return fmt.Errorf("input metadata mismatch: %v", err)
	}
	buf := make([]byte, *chunk)
	h := sha256.New()
	cpuStart, err := cpuNS()
	if err != nil {
		return err
	}
	start := time.Now()
	var count int64
	var writes int
	for {
		n, readErr := io.ReadFull(f, buf)
		if n > 0 {
			w, err := h.Write(buf[:n])
			if err != nil || w != n {
				return fmt.Errorf("hash write %d/%d: %v", w, n, err)
			}
			count += int64(n)
			writes++
		}
		if readErr == io.EOF || readErr == io.ErrUnexpectedEOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}
	sum := hex.EncodeToString(h.Sum(nil))
	wallNS := time.Since(start).Nanoseconds()
	cpuEnd, err := cpuNS()
	if err != nil {
		return err
	}
	after, err := f.Stat()
	if err != nil || before.Size() != after.Size() || before.ModTime() != after.ModTime() {
		return fmt.Errorf("input metadata changed: %v", err)
	}
	if count != *length || sum != *expected {
		return fmt.Errorf("verification failed: %d bytes %s", count, sum)
	}
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return fmt.Errorf("missing build provenance")
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{
		"input": *path, "bytes": count, "sha256": sum, "chunk": *chunk,
		"writes": writes, "hash_type": fmt.Sprintf("%T", h), "wall_ns": wallNS,
		"process_cpu_ns": cpuEnd - cpuStart, "go_version": runtime.Version(),
		"gomaxprocs": runtime.GOMAXPROCS(0), "build": info, "verified": true,
	})
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
