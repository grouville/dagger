package fsutil

import (
	"encoding/json"
	"fmt"
	"os"
	"time"
)

// Enable only on the diagnostic CLI, not the engine. One JSON record per walk
// goes to stderr; no file names or payload contents are recorded.
var profileSendWalk = os.Getenv("_DAGGER_FILESYNC_PHASE_PROFILE") == "1"

type sendWalkProfile struct {
	start       time.Time
	callbackNS  int64
	entryInfoNS int64
	sendNS      int64
	entries     uint64
}

func newSendWalkProfile() *sendWalkProfile {
	if !profileSendWalk {
		return nil
	}
	return &sendWalkProfile{start: time.Now()}
}

func (p *sendWalkProfile) finish(err error) {
	if p == nil {
		return
	}
	elapsed := time.Since(p.start).Nanoseconds()
	// Callback timings are disjoint, on one walk goroutine. The remainder is
	// filesystem enumeration, wrapper/filter work, and scheduling, not CPU time.
	record := struct {
		Kind          string `json:"kind"`
		Entries       uint64 `json:"entries"`
		WalkNS        int64  `json:"walk_ns"`
		EnumerateNS   int64  `json:"enumerate_filter_ns"`
		EntryInfoNS   int64  `json:"entry_info_ns"`
		BookkeepingNS int64  `json:"packet_bookkeeping_ns"`
		SendNS        int64  `json:"stat_send_ns"`
		Failed        bool   `json:"failed"`
	}{
		Kind:          "filesync.client.walk",
		Entries:       p.entries,
		WalkNS:        elapsed,
		EnumerateNS:   elapsed - p.callbackNS,
		EntryInfoNS:   p.entryInfoNS,
		BookkeepingNS: p.callbackNS - p.entryInfoNS - p.sendNS,
		SendNS:        p.sendNS,
		Failed:        err != nil,
	}
	data, marshalErr := json.Marshal(record)
	if marshalErr == nil {
		fmt.Fprintln(os.Stderr, string(data))
	}
}
