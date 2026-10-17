package server

import (
	"context"
	"testing"
	"time"

	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/clientdb"
	"github.com/dagger/dagger/engine/engineutil"
	"github.com/stretchr/testify/require"
)

func TestNestedClientRuntimeInitializationsCanOverlap(t *testing.T) {
	t.Parallel()
	srv, sess, parent, ctx, requestScope := newNestedTransportTestFixture(t)
	defer requestScope.Lease().Release()
	srv.clientDBs = clientdb.NewDBs(t.TempDir())
	sess.telemetryPubSub = NewPubSub(srv)
	t.Cleanup(func() { require.NoError(t, srv.clientDBs.Close()) })
	// The gateway is already initialized in a normal session. Block schema work,
	// after request admission, so the test does not depend on its runtime cost.
	sess.engineUtilClient = new(engineutil.Client)
	srv.coreSchemaBaseMu.Lock()
	initCtx, cancel := context.WithCancel(context.Background())
	results := make(chan error, 2)
	started := 0
	defer func() {
		cancel()
		srv.coreSchemaBaseMu.Unlock()
		for range started {
			select {
			case err := <-results:
				require.Error(t, err)
			case <-time.After(5 * time.Second):
				t.Error("client initialization did not finish after cancellation")
			}
		}
	}()
	var clients []*clientRuntime
	var transports []*engine.NestedClientTransport
	for _, name := range []string{"first", "second"} {
		metadata := nestedTransportTestMetadata(name)
		transport, err := srv.RegisterNestedClientTransport(ctx, metadata, parent.clientID)
		require.NoError(t, err)
		defer transport.Close()
		transports = append(transports, transport)
		child := sess.clientRuntimes[name]
		clients = append(clients, child)
		started++
		go func() {
			_, cleanup, err := srv.getOrInitClient(initCtx, &ClientInitOpts{
				ClientMetadata: metadata, NestedTransport: transport, ParentClientID: parent.clientID,
			})
			if cleanup != nil {
				_ = cleanup()
			}
			results <- err
		}()
		require.Eventually(t, func() bool {
			if !sess.scopeMu.TryLock() {
				return false
			}
			defer sess.scopeMu.Unlock()
			for _, client := range clients {
				if client.stateMu.TryLock() {
					client.stateMu.Unlock()
					return false
				}
			}
			return true
		}, time.Second, time.Millisecond, "unrelated client initializations were serialized")
	}
	// Closing either transport cannot discard a runtime while its admitted
	// initialization still owns a request lease.
	for i, child := range clients {
		transports[i].Close()
		_, _, leases := sess.clientLifecycleSnapshot(child)
		require.Equal(t, []clientLifecycleLeaseRecord{{kind: engine.ClientLeaseRequest, ownerID: "client connection"}}, leases)
	}
}

func TestInitializeSessionEngineClientConcurrent(t *testing.T) {
	t.Parallel()
	srv := &Server{engineUtilOpts: &engineutil.Opts{}}
	sess := &daggerSession{}
	start := make(chan struct{})
	type result struct {
		client *engineutil.Client
		err    error
	}
	results := make(chan result, 16)
	for range cap(results) {
		go func() {
			<-start
			err := srv.initializeSessionEngineClient(t.Context(), sess)
			results <- result{sess.engineUtilClient, err}
		}()
	}
	close(start)
	var shared *engineutil.Client
	for range cap(results) {
		r := <-results
		require.NoError(t, r.err)
		require.NotNil(t, r.client)
		if shared == nil {
			shared = r.client
		}
		require.Same(t, shared, r.client, "client runtimes must share one session gateway")
	}
}
