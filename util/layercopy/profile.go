package layercopy

import "time"

// CopyProfile is an opt-in diagnostic collector for sequential Copier work.
// It is not safe for concurrent use. Timings are aggregate Go-operation wall
// work, not CPU time, syscall time, or a critical path. Inclusive buckets
// overlap their children and must not be added to them.
type CopyProfile struct {
	Operations map[string]CopyWork `json:"operations"`
}

type CopyWork struct {
	Calls       int64 `json:"calls"`
	Nanoseconds int64 `json:"nanoseconds"`
	Bytes       int64 `json:"bytes,omitempty"`
}

func (p *CopyProfile) measure(operation string) func() {
	if p == nil {
		return func() {}
	}
	started := time.Now()
	return func() {
		elapsed := time.Since(started)
		if p.Operations == nil {
			p.Operations = make(map[string]CopyWork)
		}
		work := p.Operations[operation]
		work.Calls++
		work.Nanoseconds += elapsed.Nanoseconds()
		p.Operations[operation] = work
	}
}

func (p *CopyProfile) addBytes(operation string, bytes int64) {
	if p == nil {
		return
	}
	if p.Operations == nil {
		p.Operations = make(map[string]CopyWork)
	}
	work := p.Operations[operation]
	work.Bytes += bytes
	p.Operations[operation] = work
}
