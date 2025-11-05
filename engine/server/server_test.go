package server

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestInitLocalStateCreatesDirectories(t *testing.T) {
	t.Parallel()

	root := t.TempDir()

	srv := &Server{}
	srv.rootDir = root
	srv.solverCacheDBPath = filepath.Join(root, "cache.db")
	srv.workerRootDir = filepath.Join(root, "worker")
	srv.snapshotterRootDir = filepath.Join(srv.workerRootDir, "snapshots")
	srv.snapshotterDBPath = filepath.Join(srv.snapshotterRootDir, "metadata.db")
	srv.contentStoreRootDir = filepath.Join(srv.workerRootDir, "content")
	srv.containerdMetaDBPath = filepath.Join(srv.workerRootDir, "containerdmeta.db")
	srv.workerCacheMetaDBPath = filepath.Join(srv.workerRootDir, "metadata_v2.db")
	srv.buildkitMountPoolDir = filepath.Join(srv.workerRootDir, "cachemounts")
	srv.executorRootDir = filepath.Join(srv.workerRootDir, "executor")

	// Sanity check: paths do not exist yet.
	_, err := os.Stat(srv.snapshotterDBPath)
	require.ErrorIs(t, err, fs.ErrNotExist)
	_, err = os.Stat(srv.containerdMetaDBPath)
	require.ErrorIs(t, err, fs.ErrNotExist)

	// Ensure resources are closed after the test runs.
	t.Cleanup(func() {
		if srv.snapshotterMDStore != nil {
			require.NoError(t, srv.snapshotterMDStore.Close())
		}
		if srv.containerdMetaBoltDB != nil {
			require.NoError(t, srv.containerdMetaBoltDB.Close())
		}
		if srv.workerCacheMetaDB != nil {
			require.NoError(t, srv.workerCacheMetaDB.Close())
		}
		if srv.solverCacheDB != nil {
			require.NoError(t, srv.solverCacheDB.Close())
		}
	})

	require.NoError(t, srv.initLocalState())

	// Directories required by initBoltDBs should now exist.
	require.DirExists(t, srv.workerRootDir)
	require.DirExists(t, srv.snapshotterRootDir)
	require.DirExists(t, srv.contentStoreRootDir)
	require.DirExists(t, srv.executorRootDir)

	// Stores should be initialized so the server holds usable handles.
	require.NotNil(t, srv.snapshotterMDStore)
	require.NotNil(t, srv.containerdMetaBoltDB)
	require.NotNil(t, srv.workerCacheMetaDB)
	require.NotNil(t, srv.solverCacheDB)
}

func TestInitLocalStateFailsWithoutDirectories(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	workerRoot := filepath.Join(root, "worker")
	snapshotterRoot := filepath.Join(workerRoot, "snapshots")

	srv := &Server{
		rootDir:               root,
		solverCacheDBPath:     filepath.Join(root, "cache.db"),
		workerRootDir:         workerRoot,
		snapshotterRootDir:    snapshotterRoot,
		snapshotterDBPath:     filepath.Join(snapshotterRoot, "metadata.db"),
		contentStoreRootDir:   filepath.Join(workerRoot, "content"),
		containerdMetaDBPath:  filepath.Join(workerRoot, "containerdmeta.db"),
		workerCacheMetaDBPath: filepath.Join(workerRoot, "metadata_v2.db"),
		executorRootDir:       filepath.Join(workerRoot, "executor"),
	}

	// Delete any auto-created directories to simulate a pristine root.
	require.NoError(t, os.RemoveAll(workerRoot))
	require.NoError(t, os.RemoveAll(snapshotterRoot))

	err := srv.initBoltDBs()
	require.Error(t, err)
	require.True(t, errors.Is(err, fs.ErrNotExist) || errors.Is(err, os.ErrNotExist))
}
