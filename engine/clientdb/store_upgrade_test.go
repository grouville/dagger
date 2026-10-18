package clientdb

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/require"
)

// The visible byte can reach the filesystem cache before it is durable.
// Simulate a crash by inspecting only durableVersion after an upgrade.
type headerFile struct {
	visibleVersion byte
	durableVersion byte
	writeErr       error
	syncErr        error
}

func (f *headerFile) WriteAt(data []byte, offset int64) (int, error) {
	if f.writeErr != nil {
		return 0, f.writeErr
	}
	if len(data) != 1 || offset != 0 {
		return 0, errors.New("unexpected header write")
	}
	f.visibleVersion = data[0]
	return 1, nil
}

func (f *headerFile) Sync() error {
	if f.syncErr != nil {
		return f.syncErr
	}
	f.durableVersion = f.visibleVersion
	return nil
}

func TestStoreUpgradeMakesVersionDurableBeforeAppend(t *testing.T) {
	file := &headerFile{visibleVersion: 1, durableVersion: 1}
	require.NoError(t, upgradeStoreHeader(file))
	require.Equal(t, storeFormatVersion, file.durableVersion)
}

func TestStoreUpgradeStopsOnWriteOrSyncFailure(t *testing.T) {
	failed := errors.New("storage failure")
	for _, file := range []*headerFile{
		{visibleVersion: 1, durableVersion: 1, writeErr: failed},
		{visibleVersion: 1, durableVersion: 1, syncErr: failed},
	} {
		require.ErrorIs(t, upgradeStoreHeader(file), failed)
		require.Equal(t, byte(1), file.durableVersion)
	}
}
