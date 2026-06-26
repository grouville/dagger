package main

import (
	"fmt"
	"io"
	"net"
	"os"
)

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(args []string, stdin io.Reader, stdout io.Writer) error {
	if len(args) != 2 {
		return fmt.Errorf("usage: dagger-git-credential-helper SOCKET OPERATION")
	}
	if args[1] != "get" {
		return nil
	}

	conn, err := net.Dial("unix", args[0])
	if err != nil {
		return fmt.Errorf("failed to connect to git credential socket: %w", err)
	}
	defer conn.Close()

	errc := make(chan error, 1)
	go func() {
		_, err := io.Copy(conn, stdin)
		if unix, ok := conn.(*net.UnixConn); ok {
			_ = unix.CloseWrite()
		}
		errc <- err
	}()

	if _, err := io.Copy(stdout, conn); err != nil {
		return err
	}
	return <-errc
}
