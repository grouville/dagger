package engine

import (
	"bufio"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"strings"
	"time"
)

// A token-protected TCP listener runs a short mutual challenge-response
// before any protocol byte: the engine sends a nonce, the client answers
// with an HMAC of both nonces under the token plus its own nonce, and the
// engine answers with its own HMAC. Neither side ever sends the token, so a
// process that binds the port while the engine is down learns nothing it
// can reuse and cannot pass for the engine; the client aborts before it
// sends anything else. Checking at the listener covers gRPC, the HTTP/1
// session upgrade and HTTP/2 alike without touching any of them.
const (
	endpointChallengePrefix = "DAGGER-ENGINE-CHALLENGE "
	endpointProofPrefix     = "DAGGER-ENGINE-PROOF "
	endpointOKPrefix        = "DAGGER-ENGINE-OK "
	endpointNonceLen        = 16
	endpointMaxLine         = 256
	// The engine gives a client this long to answer its challenge.
	endpointHandshakeWindow = 10 * time.Second
	// EndpointHandshakeTimeout bounds the client side: an engine answers on
	// loopback at once, so a peer that is silent for this long is not one.
	EndpointHandshakeTimeout = 3 * time.Second
)

func endpointNonce() ([]byte, error) {
	n := make([]byte, endpointNonceLen)
	_, err := rand.Read(n)
	return n, err
}

func endpointProof(token, role string, first, second []byte) []byte {
	mac := hmac.New(sha256.New, []byte(token))
	mac.Write([]byte(role))
	mac.Write(first)
	mac.Write(second)
	return mac.Sum(nil)
}

func readEndpointLine(r *bufio.Reader, prefix string) (string, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return "", err
	}
	if len(line) > endpointMaxLine || !strings.HasPrefix(line, prefix) {
		return "", errors.New("unexpected engine handshake line")
	}
	return strings.TrimSuffix(strings.TrimPrefix(line, prefix), "\n"), nil
}

// EndpointHandshake runs the client side of the handshake on conn and
// returns once the engine has proven it holds the token.
func EndpointHandshake(conn net.Conn, token string, timeout time.Duration) error {
	_ = conn.SetDeadline(time.Now().Add(timeout))
	defer conn.SetDeadline(time.Time{})
	r := bufio.NewReaderSize(conn, endpointMaxLine)
	challenge, err := readEndpointLine(r, endpointChallengePrefix)
	if err != nil {
		return fmt.Errorf("engine handshake: %w", err)
	}
	serverNonce, err := hex.DecodeString(challenge)
	if err != nil || len(serverNonce) != endpointNonceLen {
		return errors.New("engine handshake: bad challenge")
	}
	clientNonce, err := endpointNonce()
	if err != nil {
		return err
	}
	proof := endpointProof(token, "client", serverNonce, clientNonce)
	if _, err := fmt.Fprintf(conn, "%s%s %s\n", endpointProofPrefix, hex.EncodeToString(clientNonce), hex.EncodeToString(proof)); err != nil {
		return fmt.Errorf("engine handshake: %w", err)
	}
	ok, err := readEndpointLine(r, endpointOKPrefix)
	if err != nil {
		return fmt.Errorf("engine handshake: %w", err)
	}
	serverProof, err := hex.DecodeString(ok)
	if err != nil || !hmac.Equal(serverProof, endpointProof(token, "server", clientNonce, serverNonce)) {
		return errors.New("engine handshake: the peer does not hold the engine token")
	}
	if r.Buffered() != 0 {
		return errors.New("engine handshake: unexpected data after handshake")
	}
	return nil
}

// EndpointTokenDial dials addr and completes the handshake.
func EndpointTokenDial(network, addr, token string, timeout time.Duration) (net.Conn, error) {
	conn, err := net.DialTimeout(network, addr, timeout)
	if err != nil {
		return nil, err
	}
	if err := EndpointHandshake(conn, token, timeout); err != nil {
		conn.Close()
		return nil, err
	}
	return conn, nil
}

// NewTokenListener wraps l so that only connections that complete the
// handshake for token get through Accept. Connections that fail it, or do
// not finish it in time, are closed; the wrapped listener keeps accepting.
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
		go tl.handshake(conn)
	}
}

func (tl *tokenListener) handshake(conn net.Conn) {
	_ = conn.SetDeadline(time.Now().Add(endpointHandshakeWindow))
	serverNonce, err := endpointNonce()
	if err != nil {
		conn.Close()
		return
	}
	if _, err := fmt.Fprintf(conn, "%s%s\n", endpointChallengePrefix, hex.EncodeToString(serverNonce)); err != nil {
		conn.Close()
		return
	}
	r := bufio.NewReaderSize(conn, endpointMaxLine)
	proofLine, err := readEndpointLine(r, endpointProofPrefix)
	if err != nil {
		conn.Close()
		return
	}
	nonceHex, proofHex, ok := strings.Cut(proofLine, " ")
	clientNonce, err1 := hex.DecodeString(nonceHex)
	proof, err2 := hex.DecodeString(proofHex)
	if !ok || err1 != nil || err2 != nil || len(clientNonce) != endpointNonceLen ||
		subtle.ConstantTimeCompare(proof, endpointProof(tl.token, "client", serverNonce, clientNonce)) != 1 {
		conn.Close()
		return
	}
	if _, err := fmt.Fprintf(conn, "%s%s\n", endpointOKPrefix, hex.EncodeToString(endpointProof(tl.token, "server", clientNonce, serverNonce))); err != nil {
		conn.Close()
		return
	}
	_ = conn.SetDeadline(time.Time{})
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

// bufferedConn serves any bytes the handshake reader buffered past the
// last line before reading from the connection again.
type bufferedConn struct {
	net.Conn
	r *bufio.Reader
}

func (c *bufferedConn) Read(p []byte) (int, error) { return c.r.Read(p) }

var _ io.Reader = (*bufferedConn)(nil)
