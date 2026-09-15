package snapshots

import (
	"context"
	"errors"
	"testing"

	"github.com/containerd/containerd/v2/core/leases"
	cerrdefs "github.com/containerd/errdefs"
	"github.com/stretchr/testify/require"
)

type retryDeleteLeaseManager struct {
	leases.Manager
	deleteErr   error
	deleteCalls int
}

func (m *retryDeleteLeaseManager) Delete(ctx context.Context, lease leases.Lease, opts ...leases.DeleteOpt) error {
	m.deleteCalls++
	if m.deleteErr != nil {
		return m.deleteErr
	}
	return m.Manager.Delete(ctx, lease, opts...)
}

func TestLazyLeaseReleaseRetriesFailedDeletion(t *testing.T) {
	f := newContentOwnerFixture(t)
	lm := &retryDeleteLeaseManager{Manager: f.cm.LeaseManager}
	ctx, release, err := WithLazyLease(f.ctx, lm)
	require.NoError(t, err)
	leaseCtx, err := EnsureLease(ctx)
	require.NoError(t, err)
	leaseID, ok := leases.FromContext(leaseCtx)
	require.True(t, ok)
	deleteErr := errors.New("temporary lease deletion failure")
	lm.deleteErr = deleteErr
	require.ErrorIs(t, release(f.ctx), deleteErr)
	_, err = EnsureLease(ctx)
	require.ErrorContains(t, err, "already released", "failed cleanup must not reopen the scope")
	resources, err := lm.ListResources(f.ctx, leases.Lease{ID: leaseID})
	require.NoError(t, err, "failed deletion must retain the lease")
	require.Empty(t, resources)

	lm.deleteErr = nil
	require.NoError(t, release(f.ctx))
	require.Equal(t, 2, lm.deleteCalls)
	_, err = lm.ListResources(f.ctx, leases.Lease{ID: leaseID})
	require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	require.NoError(t, release(f.ctx))
	require.Equal(t, 2, lm.deleteCalls, "successful deletion must not be repeated")
	_, err = EnsureLease(ctx)
	require.ErrorContains(t, err, "already released")
}

func TestLazyLeaseReleaseAlreadyDeleted(t *testing.T) {
	f := newContentOwnerFixture(t)
	lm := &retryDeleteLeaseManager{Manager: f.cm.LeaseManager}
	ctx, release, err := WithLazyLease(f.ctx, lm)
	require.NoError(t, err)
	leaseCtx, err := EnsureLease(ctx)
	require.NoError(t, err)
	leaseID, ok := leases.FromContext(leaseCtx)
	require.True(t, ok)
	require.NoError(t, f.cm.LeaseManager.Delete(f.ctx, leases.Lease{ID: leaseID}))
	require.NoError(t, release(f.ctx), "NotFound means cleanup already completed")
	require.NoError(t, release(f.ctx))
	require.Equal(t, 1, lm.deleteCalls)
	_, err = EnsureLease(ctx)
	require.ErrorContains(t, err, "already released")
}

func TestLazyLeaseReleaseBeforeCreation(t *testing.T) {
	f := newContentOwnerFixture(t)
	lm := &retryDeleteLeaseManager{Manager: f.cm.LeaseManager}
	ctx, release, err := WithLazyLease(f.ctx, lm)
	require.NoError(t, err)
	require.NoError(t, release(f.ctx))
	require.NoError(t, release(f.ctx))
	require.Zero(t, lm.deleteCalls)
	_, err = EnsureLease(ctx)
	require.ErrorContains(t, err, "already released")
}
