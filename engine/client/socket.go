package client

import (
	"github.com/dagger/dagger/engine/session/attachables"
	"github.com/dagger/dagger/internal/buildkit/session/sshforward"
)

type SocketProvider = attachables.SocketProvider
type SocketSessionProxy = attachables.SocketSessionProxy

func NewSocketSessionProxy(client sshforward.SSHClient) *SocketSessionProxy {
	return attachables.NewSocketSessionProxy(client)
}
