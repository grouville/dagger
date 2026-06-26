package sdk

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"io"
	"net"
	"slices"
	"strings"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/engineutil"
	gitsession "github.com/dagger/dagger/engine/session/git"
	"github.com/opencontainers/go-digest"
	gomodule "golang.org/x/mod/module"
)

// During Go SDK codegen, `go mod download` runs git over HTTPS for private modules. We
// give that git a credential helper backed by the host's own credentials:
//
//	git (in container) -> dagger-git-credential-helper -> unix socket
//	  -> goSDKGitCredentialProvider (here) -> bk.GetCredential -> host `git credential fill`
//
// The provider only answers for hosts/paths matching GOPRIVATE — the same rule go uses to
// decide what's private — so a dependency can't fish for credentials to other hosts. The
// generic "engine-served socket" plumbing lives in core/socket_mount_provider.go.

const goSDKGitCredentialSocketDigestVersion = "go-sdk-git-credential-socket-v1"

type goSDKGitCredentialProvider struct {
	patterns  string   // GOPRIVATE patterns; the credential allowlist
	clientIDs []string // client sessions to ask for credentials, first match wins
}

func newGoSDKGitCredentialProvider(patterns string, clientIDs []string) *goSDKGitCredentialProvider {
	return &goSDKGitCredentialProvider{patterns: patterns, clientIDs: slices.Clone(clientIDs)}
}

// MountSocket serves the git credential protocol on a fresh unix socket (see
// core.SocketMountProvider).
func (p *goSDKGitCredentialProvider) MountSocket(ctx context.Context) (string, func() error, error) {
	query, err := core.CurrentQuery(ctx)
	if err != nil {
		return "", nil, err
	}
	bk, err := query.Engine(ctx)
	if err != nil {
		return "", nil, err
	}
	return core.ServeLocalUnixSocket(ctx, ".dagger-git-credential", func(ctx context.Context, conn net.Conn) {
		p.answer(ctx, bk, conn)
	})
}

// answer handles one git credential request. On any failure it writes nothing, which git
// reads as "no credentials" — i.e. it fails closed.
func (p *goSDKGitCredentialProvider) answer(ctx context.Context, bk *engineutil.Client, conn io.ReadWriter) {
	req, err := gitsession.ReadCredentialRequest(conn)
	if err != nil || !p.allowed(req) {
		return
	}
	cred, err := p.lookup(ctx, bk, req)
	if err != nil {
		return
	}
	_ = gitsession.WriteCredential(conn, cred)
}

// allowed reports whether req targets a GOPRIVATE host/path over HTTP(S), matched exactly
// as go matches GOPRIVATE.
func (p *goSDKGitCredentialProvider) allowed(req *gitsession.GitCredentialRequest) bool {
	if req.GetProtocol() != "http" && req.GetProtocol() != "https" {
		return false
	}
	if req.GetHost() == "" {
		return false
	}
	target := req.GetHost()
	if path := strings.Trim(req.GetPath(), "/"); path != "" {
		target += "/" + path
	}
	return gomodule.MatchPrefixPatterns(p.patterns, target)
}

// lookup asks each client session for the credential, preferring a per-repo match (with
// path) and falling back to a host-level one.
func (p *goSDKGitCredentialProvider) lookup(ctx context.Context, bk *engineutil.Client, req *gitsession.GitCredentialRequest) (*gitsession.CredentialInfo, error) {
	path := strings.Trim(req.GetPath(), "/")
	for _, clientID := range p.clientIDs {
		authCtx := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{ClientID: clientID})
		cred, err := bk.GetCredential(authCtx, req.GetProtocol(), req.GetHost(), path)
		if err != nil && path != "" {
			cred, err = bk.GetCredential(authCtx, req.GetProtocol(), req.GetHost(), "")
		}
		if err == nil {
			return cred, nil
		}
	}
	return nil, fmt.Errorf("no git credentials for %s", req.GetHost())
}

// goSDKGitCredentialHandle derives the session-resource handle the provider is bound to:
// a salted, order-independent identity over (patterns, clientIDs).
func goSDKGitCredentialHandle(secretSalt []byte, patterns string, clientIDs []string) dagql.SessionResourceHandle {
	clientIDs = slices.Clone(clientIDs)
	slices.Sort(clientIDs)

	// Values can't contain newlines, so newline-delimiting them is unambiguous.
	mac := hmac.New(sha256.New, secretSalt)
	fmt.Fprintln(mac, goSDKGitCredentialSocketDigestVersion)
	fmt.Fprintln(mac, patterns)
	for _, clientID := range clientIDs {
		fmt.Fprintln(mac, clientID)
	}
	return dagql.SessionResourceHandle(digest.NewDigestFromBytes(digest.SHA256, mac.Sum(nil)))
}
