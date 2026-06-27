package core

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/opencontainers/go-digest"
)

// A "mount-provider" socket is a unix socket that the engine serves itself, rather than
// forwarding one from the client (the way an SSH agent socket is forwarded). The Go SDK
// uses one to answer git credential requests during codegen.
//
// The three steps, in order of use:
//   - NewMountProviderSocketID: create a Socket bound to a SocketMountProvider and get its
//     ID, to hand to withUnixSocket.
//   - Socket.Mount: called by the exec machinery at mount time; finds the bound provider
//     and asks it to open the socket.
//   - ServeLocalUnixSocket: the helper a provider uses to actually run that socket.

// SocketKindMountProvider is an engine-served socket whose handle resolves to a bound
// SocketMountProvider, rather than a client-forwarded unix/ssh socket.
const SocketKindMountProvider SocketKind = "mount_provider"

// SocketMountProvider opens the unix socket for a SocketKindMountProvider socket and
// returns its path plus a cleanup func. Implemented outside core (e.g. by the Go SDK) and
// bound as a session resource under the socket's handle.
type SocketMountProvider interface {
	MountSocket(ctx context.Context) (string, func() error, error)
}

// NewMountProviderSocketID binds provider as a session resource under handle and returns
// the ID of a socket that resolves back to it. Pass the ID to withUnixSocket to mount the
// served socket into a container.
func NewMountProviderSocketID(ctx context.Context, dag *dagql.Server, handle dagql.SessionResourceHandle, provider SocketMountProvider) (*call.ID, error) {
	clientMetadata, err := engine.ClientMetadataFromContext(ctx)
	if err != nil {
		return nil, err
	}
	cache, err := dagql.EngineCache(ctx)
	if err != nil {
		return nil, err
	}

	// Wrap the socket value as a dagql result, content-addressed by its handle and tagged
	// as a session resource.
	socket := &Socket{Kind: SocketKindMountProvider, Handle: handle}
	inst, err := dagql.NewResultForCall(socket, &dagql.ResultCall{
		Kind:        dagql.ResultCallKindSynthetic,
		SyntheticOp: "mount-provider-socket",
		Type:        dagql.NewResultCallType(socket.Type()),
	})
	if err != nil {
		return nil, err
	}
	if inst, err = inst.WithContentDigest(ctx, digest.Digest(handle)); err != nil {
		return nil, err
	}
	if inst, err = inst.WithSessionResourceHandle(ctx, handle); err != nil {
		return nil, err
	}

	// Bind the provider under the handle (so Socket.Mount can resolve it at mount time),
	// then attach the result to the session to obtain its ID.
	if err := cache.BindSessionResource(ctx, clientMetadata.SessionID, clientMetadata.ClientID, handle, provider); err != nil {
		return nil, err
	}
	attached, err := cache.AttachResult(ctx, clientMetadata.SessionID, dag, inst)
	if err != nil {
		return nil, err
	}
	idable, ok := dagql.UnwrapAs[dagql.IDable](attached)
	if !ok {
		return nil, fmt.Errorf("unexpected mount provider socket result %T", attached)
	}
	return idable.ID()
}

// Mount returns the unix socket path to mount for this socket, plus a cleanup func.
// Provider-backed sockets are served by their bound provider; everything else (ssh agent
// and forwarded unix sockets) is byte-stream forwarded by MountSSHAgent.
func (socket *Socket) Mount(ctx context.Context) (string, func() error, error) {
	if socket == nil {
		return "", nil, errors.New("socket is nil")
	}
	if socket.Kind != SocketKindMountProvider {
		return socket.MountSSHAgent(ctx)
	}

	clientMetadata, err := engine.ClientMetadataFromContext(ctx)
	if err != nil {
		return "", nil, err
	}
	cache, err := dagql.EngineCache(ctx)
	if err != nil {
		return "", nil, err
	}
	resolved, err := cache.ResolveSessionResource(ctx, clientMetadata.SessionID, clientMetadata.ClientID, socket.Handle)
	if err != nil {
		return "", nil, fmt.Errorf("resolve mount provider socket %q: %w", socket.Handle, err)
	}
	provider, ok := resolved.(SocketMountProvider)
	if !ok {
		return "", nil, fmt.Errorf("socket %q resolved to %T, not a mount provider", socket.Handle, resolved)
	}
	return provider.MountSocket(ctx)
}

// ServeLocalUnixSocket listens on a unix socket in a fresh temp dir and serves each
// connection with handle, returning the socket path and a cleanup func. Serving stops on
// cleanup or ctx cancellation. SocketMountProvider implementations use this for the
// listener boilerplate.
func ServeLocalUnixSocket(ctx context.Context, namePrefix string, handle func(ctx context.Context, conn net.Conn)) (_ string, _ func() error, err error) {
	dir, err := os.MkdirTemp("", namePrefix)
	if err != nil {
		return "", nil, err
	}
	defer func() {
		if err != nil {
			_ = os.RemoveAll(dir)
		}
	}()
	if err = os.Chmod(dir, 0o711); err != nil {
		return "", nil, err
	}

	sockPath := filepath.Join(dir, "sock")
	listener, err := net.Listen("unix", sockPath)
	if err != nil {
		return "", nil, err
	}

	ctx, cancel := context.WithCancel(ctx)
	context.AfterFunc(ctx, func() { _ = listener.Close() })
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return // listener closed
			}
			go func() {
				defer conn.Close()
				handle(ctx, conn)
			}()
		}
	}()

	return sockPath, func() error {
		cancel()
		return os.RemoveAll(dir)
	}, nil
}
