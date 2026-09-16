package filesync

import (
	"context"
	"encoding/json"
	"io"
	"sync/atomic"
	"time"

	"github.com/containerd/continuity/sysx"
	bkcontenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/dagger/dagger/internal/buildkit/util/bklog"
)

// These are overlapping, inclusive Go-operation wall-work aggregates, not
// critical-path intervals or syscall timings. Concurrent file work can exceed
// elapsed sync time. Caller-inclusive scopes include change-cache wait; worker
// operations belong to the sync which started that shared work.
type syncWorkProfile struct {
	counters [syncWorkCount]syncWorkCounter
}

type syncWorkCounter struct {
	calls       atomic.Int64
	nanoseconds atomic.Int64
	bytes       atomic.Int64
}

type syncWorkKind int

const (
	syncWorkHandleChange syncWorkKind = iota
	syncWorkPrevious
	syncWorkPreviousXattr
	syncWorkWrite
	syncWorkPayloadOpen
	syncWorkPayloadCopy
	syncWorkCount
)

var syncWorkNames = [...]string{
	"hash.handle_change",
	"previous.inclusive",
	"previous.hash_xattr",
	"write.inclusive",
	"payload.open",
	"payload.receive_write_hash",
}

type syncWorkContextKey struct{}

func startSyncWorkProfile(ctx context.Context) (context.Context, *syncWorkProfile) {
	if !wcprof.Enabled(ctx) {
		return ctx, nil
	}
	p := &syncWorkProfile{}
	return context.WithValue(ctx, syncWorkContextKey{}, p), p
}

func syncWorkFromContext(ctx context.Context) *syncWorkProfile {
	p, _ := ctx.Value(syncWorkContextKey{}).(*syncWorkProfile)
	return p
}

func (p *syncWorkProfile) measure(kind syncWorkKind) func() {
	if p == nil {
		return func() {}
	}
	started := time.Now()
	return func() {
		p.counters[kind].nanoseconds.Add(time.Since(started).Nanoseconds())
		p.counters[kind].calls.Add(1)
	}
}

func logSyncWorkProfile(ctx context.Context, p *syncWorkProfile, forParents bool, syncErr error) {
	if p == nil {
		return
	}
	type work struct {
		Calls       int64 `json:"calls"`
		Nanoseconds int64 `json:"nanoseconds"`
		Bytes       int64 `json:"bytes,omitempty"`
	}
	result := struct {
		ForParents bool            `json:"for_parents"`
		Failed     bool            `json:"failed"`
		Operations map[string]work `json:"operations"`
	}{ForParents: forParents, Failed: syncErr != nil, Operations: make(map[string]work)}
	for i := range p.counters {
		c := &p.counters[i]
		result.Operations[syncWorkNames[i]] = work{
			Calls: c.calls.Load(), Nanoseconds: c.nanoseconds.Load(), Bytes: c.bytes.Load(),
		}
	}
	if data, err := json.Marshal(result); err == nil {
		bklog.G(ctx).Debugf("filesync.sync.work.profile %s", data)
	}
}

func profileHandleChange(ctx context.Context, cache bkcontenthash.CacheContext, kind ChangeKind, path string, stat *HashedStatInfo) error {
	defer syncWorkFromContext(ctx).measure(syncWorkHandleChange)()
	return cache.HandleChange(kind, path, stat, nil)
}

func profilePreviousHash(ctx context.Context, path string) ([]byte, error) {
	defer syncWorkFromContext(ctx).measure(syncWorkPreviousXattr)()
	return sysx.Getxattr(path, hashXattrKey)
}

func profilePayloadOpen(ctx context.Context, remote ReadFS, path string) (io.ReadCloser, error) {
	defer syncWorkFromContext(ctx).measure(syncWorkPayloadOpen)()
	return remote.ReadFile(ctx, path)
}

func profilePayloadCopy(ctx context.Context, dst io.Writer, src io.Reader, buf []byte) (int64, error) {
	p := syncWorkFromContext(ctx)
	defer p.measure(syncWorkPayloadCopy)()
	n, err := io.CopyBuffer(dst, src, buf)
	if p != nil {
		p.counters[syncWorkPayloadCopy].bytes.Add(n)
	}
	return n, err
}
