package filesync

import (
	"os"
	"path/filepath"
	"sync"

	"github.com/opencontainers/go-digest"
)

// SnapshotSeeds holds optional, bounded hints for deriving an import from a
// previous immutable snapshot. Snapshot IDs do not keep snapshots leased;
// collecting a hint's snapshot simply makes the next import use a full copy.
type SnapshotSeeds struct {
	mu      sync.Mutex
	clock   uint64
	entries map[string]snapshotSeed
	records int
}

const (
	maxSnapshotSeedScopes  = 8
	maxSnapshotSeedRecords = 64 << 10
	maxSnapshotSeedDepth   = 8
)

type snapshotSeed struct {
	id      string
	records map[string]snapshotSeedRecord
	depth   int
	used    uint64
}

type snapshotSeedRecord struct {
	digest digest.Digest
	mode   os.FileMode
}

func (s *SnapshotSeeds) get(scope string) (snapshotSeed, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	seed, ok := s.entries[scope]
	if ok {
		s.clock++
		seed.used = s.clock
		s.entries[scope] = seed
	}
	return seed, ok
}

func (s *SnapshotSeeds) put(scope string, seed snapshotSeed) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if previous, ok := s.entries[scope]; ok {
		s.records -= len(previous.records)
		delete(s.entries, scope)
	}
	if len(seed.records) == 0 || len(seed.records) > maxSnapshotSeedRecords {
		return
	}
	for len(s.entries) >= maxSnapshotSeedScopes || s.records+len(seed.records) > maxSnapshotSeedRecords {
		var oldest string
		var used uint64
		for key, value := range s.entries {
			if oldest == "" || value.used < used {
				oldest, used = key, value.used
			}
		}
		s.records -= len(s.entries[oldest].records)
		delete(s.entries, oldest)
	}
	if s.entries == nil {
		s.entries = make(map[string]snapshotSeed)
	}
	s.clock++
	seed.used = s.clock
	s.entries[scope] = seed
	s.records += len(seed.records)
}

// changedPaths compares the actual snapshot records, rather than changes to
// the shared mirror. Other filters and failed imports can also change that
// mirror between two successful imports of this scope.
func (seed snapshotSeed) changedPaths(current map[string]snapshotSeedRecord) (map[string]struct{}, bool) {
	if seed.depth >= maxSnapshotSeedDepth {
		return nil, false
	}
	for path, previous := range seed.records {
		next, ok := current[path]
		if !ok || previous.mode.Type() != next.mode.Type() {
			// This first experiment uses a full copy for removals and type
			// changes, keeping whiteout handling on the existing path.
			return nil, false
		}
	}
	changed := make(map[string]struct{})
	for path, next := range current {
		if previous, ok := seed.records[path]; !ok || previous != next {
			changed[path] = struct{}{}
		}
	}
	return changed, true
}

func (local *localFS) snapshotSeedRecords(results []CachedChange, only map[string]struct{}) map[string]snapshotSeedRecord {
	if len(only) > maxSnapshotSeedRecords {
		return nil
	}
	selected := localCopyOnlyPaths(only, local.copyPath)
	// A re-included file can have an ignored parent. The copy creates that
	// parent implicitly, so its record also belongs to the resulting tree.
	for path := range selected {
		for parent := filepath.Dir(path); parent != "." && parent != string(filepath.Separator); parent = filepath.Dir(parent) {
			if _, ok := selected[parent]; ok {
				break
			}
			selected[parent] = struct{}{}
		}
	}
	if len(selected) > maxSnapshotSeedRecords {
		return nil
	}
	base := local.toRootPath(local.copyPath)
	records := make(map[string]snapshotSeedRecord, len(selected))
	for _, result := range results {
		change := result.result()
		if change == nil || change.kind == ChangeKindDelete || change.stat == nil {
			continue
		}
		path, err := filepath.Rel(base, result.callKey)
		if err != nil {
			return nil
		}
		path = cleanLocalCopyPath(path)
		if _, ok := selected[path]; !ok {
			continue
		}
		mode := change.stat.Mode()
		if (!mode.IsDir() && !mode.IsRegular() && mode&os.ModeSymlink == 0) || (mode.IsRegular() && change.stat.Linkname != "") {
			// Preserve the existing hardlink and special-file behavior.
			return nil
		}
		records[path] = snapshotSeedRecord{digest: change.stat.Digest(), mode: mode}
	}
	return records
}
