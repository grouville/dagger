//go:build !darwin && !windows

package engineutil

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/dagger/dagger/internal/buildkit/util/network"
	"github.com/stretchr/testify/require"
)

// Telemetry listeners are created before runc starts the container. A host
// network provider must use the existing namespace without looking up its PID.
func TestRunInHostNetworkNamespace(t *testing.T) {
	GetGlobalNamespaceWorkerPool().Start()
	t.Cleanup(ShutdownGlobalNamespaceWorkerPool)

	t.Run("host listener before container start", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(t.Context(), time.Second)
		defer cancel()
		ns, err := network.NewHostProvider().New(ctx, "")
		require.NoError(t, err)
		t.Cleanup(func() { require.NoError(t, ns.Close()) })
		state := &execState{id: "not-started", done: make(chan struct{}), networkNamespace: ns}
		listener, err := runInNetNS(ctx, state, func() (net.Listener, error) {
			return net.Listen("tcp", "127.0.0.1:0")
		})
		require.NoError(t, err)
		require.NoError(t, listener.Close())
	})

	t.Run("none provider does not inherit host", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(t.Context(), time.Second)
		defer cancel()
		ns, err := network.NewNoneProvider().New(ctx, "")
		require.NoError(t, err)
		t.Cleanup(func() { require.NoError(t, ns.Close()) })
		state := &execState{id: "not-started", done: make(chan struct{}), networkNamespace: ns}
		called := false
		_, err = runInNetNS(ctx, state, func() (bool, error) {
			called = true
			return true, nil
		})
		require.Error(t, err)
		require.False(t, called)
	})
}
