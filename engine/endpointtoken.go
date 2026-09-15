package engine

import (
	"bufio"
	"crypto/subtle"
	"errors"
	"fmt"
	"io"
	"net"
	"strings"
	"time"
)

// A token-protected TCP listener requires every connection to start with
// one preamble line carrying the engine token before any protocol byte.
// Checking it at the listener covers gRPC, the HTTP/1 session upgrade and
// HTTP/2 alike without touching any of them.
const (
	endpointTokenPrefix     = "DAGGER-ENGINE-TOKEN "
	endpointTokenMaxLine    = 512
	endpointTokenReadWindow = 10 * time.Second
)

// WriteEndpointToken sends the preamble a token-protected listener expects.
func WriteEndpointToken(w io.Writer, token string) error {
	_, err := io.WriteString(w, endpointTokenPrefix+token+"\n")
	return err
}

// NewTokenListener wraps l so that only connections presenting token get
// through Accept. Connections that fail to present it in time, or present
// another one, are closed; the wrapped listener keeps accepting.
func NewTokenListener(l net.Listener, token string) net.Listener {
	tl := &tokenListener{Listener: l, token: token, conns: make(chan net.Conn), done: make(chan struct{})}
	go tl.acceptLoop()
	return tl
}

type tokenListener struct {
	net.Listener
	token string
	conns chan net.Conn
	done  chan struct{}
	err   error
}

func (tl *tokenListener) acceptLoop() {
	defer close(tl.done)
	for {
		conn, err := tl.Listener.Accept()
		if err != nil {
			tl.err = err
			return
		}
		go tl.check(conn)
	}
}

func (tl *tokenListener) check(conn net.Conn) {
	_ = conn.SetReadDeadline(time.Now().Add(endpointTokenReadWindow))
	r := bufio.NewReaderSize(conn, endpointTokenMaxLine)
	line, err := r.ReadString('\n')
	if err != nil || len(line) > endpointTokenMaxLine ||
		!strings.HasPrefix(line, endpointTokenPrefix) ||
		subtle.ConstantTimeCompare([]byte(strings.TrimSuffix(strings.TrimPrefix(line, endpointTokenPrefix), "\n")), []byte(tl.token)) != 1 {
		conn.Close()
		return
	}
	_ = conn.SetReadDeadline(time.Time{})
	select {
	case tl.conns <- &bufferedConn{Conn: conn, r: r}:
	case <-tl.done:
		conn.Close()
	}
}

func (tl *tokenListener) Accept() (net.Conn, error) {
	select {
	case conn := <-tl.conns:
		return conn, nil
	case <-tl.done:
		if tl.err != nil {
			return nil, tl.err
		}
		return nil, errors.New("listener closed")
	}
}

func (tl *tokenListener) Close() error {
	err := tl.Listener.Close()
	<-tl.done
	return err
}

// bufferedConn serves the bytes the preamble reader may have buffered past
// the newline before reading from the connection again.
type bufferedConn struct {
	net.Conn
	r *bufio.Reader
}

func (c *bufferedConn) Read(p []byte) (int, error) { return c.r.Read(p) }

// EndpointTokenDial dials addr and presents token.
func EndpointTokenDial(network, addr, token string, timeout time.Duration) (net.Conn, error) {
	conn, err := net.DialTimeout(network, addr, timeout)
	if err != nil {
		return nil, err
	}
	if err := WriteEndpointToken(conn, token); err != nil {
		conn.Close()
		return nil, fmt.Errorf("send engine token: %w", err)
	}
	return conn, nil
}
