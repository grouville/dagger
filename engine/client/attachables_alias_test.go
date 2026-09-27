package client

import (
	"net"
	"reflect"
	"testing"

	"github.com/dagger/dagger/engine/session/attachables"
	"github.com/stretchr/testify/require"
)

var (
	_ attachables.SessionAttachable = SocketProvider{}
	_ SessionAttachable             = attachables.SocketProvider{}
	_ Filesyncer                    = attachables.Filesyncer{}
	_ attachables.FilesyncSource    = FilesyncSource{}
	_ FilesyncTarget                = attachables.FilesyncTarget{}
	_ FilesyncSourceProxy           = attachables.FilesyncSourceProxy{}
	_ FilesyncTargetProxy           = attachables.FilesyncTargetProxy{}
	_ *SocketSessionProxy           = (*attachables.SocketSessionProxy)(nil)
	_ *SessionAttachablesServer     = (*attachables.SessionAttachablesServer)(nil)
)

func TestAttachablesPublicAliases(t *testing.T) {
	require.Equal(t, InstrumentationLibrary, attachables.InstrumentationLibrary)
	f, err := NewFilesyncer()
	require.NoError(t, err)
	direct, err := attachables.NewFilesyncer()
	require.NoError(t, err)
	require.Equal(t, reflect.TypeOf(direct), reflect.TypeOf(f))
	require.Equal(t, reflect.TypeOf(direct.AsSource()), reflect.TypeOf(f.AsSource()))
	require.Equal(t, reflect.TypeOf(direct.AsTarget()), reflect.TypeOf(f.AsTarget()))
	local, peer := net.Pipe()
	defer local.Close()
	defer peer.Close()
	server := NewSessionAttachablesServer(t.Context(), local, f.AsSource(), f.AsTarget(), SocketProvider{})
	defer server.Stop()
	require.Same(t, local, server.Conn)
	require.Len(t, server.Attachables, 3)
	require.Contains(t, server.MethodURLs, "/grpc.health.v1.Health/Check")
	require.Contains(t, server.MethodURLs, "/moby.sshforward.v1.SSH/ForwardAgent")
}
