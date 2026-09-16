package fsutil

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/dagger/dagger/engine/wcprof"
)

// Diagnostic only: one record per walk, not one event per file. All counters
// belong to the walk goroutine. Callback time includes nested stat/xattr work
// and downstream backpressure; these inclusive counters are not additive.
type fsWalkProfile struct {
	start time.Time
	work  map[string]*fsWalkWork
}

type fsWalkWork struct {
	Calls uint64 `json:"calls"`
	NS    int64  `json:"nanoseconds"`
}

func newFSWalkProfile(ctx context.Context) *fsWalkProfile {
	if !profileSendWalk && !wcprof.Enabled(ctx) {
		return nil
	}
	return &fsWalkProfile{start: time.Now(), work: make(map[string]*fsWalkWork)}
}

func (p *fsWalkProfile) measure(name string) func() {
	if p == nil {
		return func() {}
	}
	w := p.work[name]
	if w == nil {
		w = &fsWalkWork{}
		p.work[name] = w
	}
	start := time.Now()
	return func() {
		w.Calls++
		w.NS += time.Since(start).Nanoseconds()
	}
}

func (p *fsWalkProfile) finish(err error) {
	if p == nil {
		return
	}
	record := struct {
		Kind   string                 `json:"kind"`
		WalkNS int64                  `json:"walk_ns"`
		Failed bool                   `json:"failed"`
		Work   map[string]*fsWalkWork `json:"operations"`
	}{"filesync.fs.walk", time.Since(p.start).Nanoseconds(), err != nil, p.work}
	if data, err := json.Marshal(record); err == nil {
		fmt.Fprintln(os.Stderr, string(data))
	}
}
