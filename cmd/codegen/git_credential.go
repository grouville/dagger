package main

import (
	"fmt"
	"io"
	"net"
	"os"

	"github.com/spf13/cobra"
)

// gitCredentialCmd is a hidden git credential helper. git runs it as
//
//	codegen _git-credential <socket> <operation>
//
// with its request on stdin and the credential expected on stdout. All it does is relay
// those bytes to and from <socket> — the engine's credential server — so private Go
// module auth works during codegen without shipping a separate binary (codegen is already
// on PATH in the SDK container).
var gitCredentialCmd = &cobra.Command{
	Use:    "_git-credential SOCKET OPERATION",
	Hidden: true,
	Args:   cobra.ExactArgs(2),
	RunE: func(_ *cobra.Command, args []string) error {
		socketPath, operation := args[0], args[1]
		if operation != "get" {
			// git also calls "store"/"erase"; we only answer credential lookups.
			return nil
		}
		return relayCredential(socketPath, os.Stdin, os.Stdout)
	},
}

// relayCredential connects to the credential socket and pipes git's request (in) to it
// while streaming the response back to git (out). The server replies only once it has
// read the whole request, so half-closing the write side after sending lets it respond.
func relayCredential(socketPath string, in io.Reader, out io.Writer) error {
	conn, err := net.Dial("unix", socketPath)
	if err != nil {
		return fmt.Errorf("connect to git credential socket: %w", err)
	}
	defer conn.Close()

	go func() {
		_, _ = io.Copy(conn, in)
		if unixConn, ok := conn.(*net.UnixConn); ok {
			_ = unixConn.CloseWrite()
		}
	}()

	_, err = io.Copy(out, conn)
	return err
}
