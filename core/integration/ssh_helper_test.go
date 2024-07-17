package core

import (
	"io"
	"net"
	"os"
	"path/filepath"

	"github.com/dagger/dagger/testctx"
	"github.com/stretchr/testify/require"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/agent"
)

var (
	globalSSHAgent        agent.Agent
	globalSSHSock         string
	globalHostSSHAuthSock string
)

func setupGlobalSSHAgent(t *testctx.T) func() {
	// Use t for logging and error reporting
	t.Log("Setting up global SSH agent")

	key, err := ssh.ParseRawPrivateKey([]byte(globalPrivateKeyReadOnly))
	require.NoError(t, err)

	globalSSHAgent = agent.NewKeyring()
	err = globalSSHAgent.Add(agent.AddedKey{
		PrivateKey: key,
	})
	require.NoError(t, err)

	tmp := t.TempDir()
	globalSSHSock = filepath.Join(tmp, "ssh-agent.sock")
	l, err := net.Listen("unix", globalSSHSock)
	require.NoError(t, err)

	go func() {
		for {
			conn, err := l.Accept()
			if err != nil {
				t.Logf("SSH agent l stopped: %v", err)
				return
			}
			go func() {
				defer conn.Close()
				err := agent.ServeAgent(globalSSHAgent, conn)
				if err != nil && err != io.EOF {
					t.Logf("SSH agent error: %v", err)
				}
			}()
		}
	}()

	// ensure test suite is not polluted by env var
	globalHostSSHAuthSock = os.Getenv("SSH_AUTH_SOCK")
	os.Unsetenv("SSH_AUTH_SOCK")

	return func() {
		t.Log("Cleaning up global SSH agent")
		l.Close()
		os.Remove(globalSSHSock)
		// leave host environment untouched
		if globalHostSSHAuthSock != "" {
			os.Setenv("SSH_AUTH_SOCK", globalHostSSHAuthSock)
		}
	}
}
