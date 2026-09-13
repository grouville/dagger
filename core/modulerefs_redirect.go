package core

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/dagger/dagger/core/gitref"
	"github.com/dagger/dagger/core/workspace"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/slog"
)

const (
	// daggerGetQueryParam is the query flag appended to a module ref to probe
	// for a redirect that points at the real module source.
	daggerGetQueryParam = "dagger-get"

	// daggerGetProbeTimeout bounds the redirect probe so a slow or hanging host
	// cannot block module resolution.
	daggerGetProbeTimeout = 5 * time.Second
)

// daggerGetClient issues the redirect probe. It never follows redirects itself:
// we must read the Location header and rewrite it (stripping dagger-get,
// re-appending any version) before continuing resolution.
var daggerGetClient = &http.Client{
	Timeout: daggerGetProbeTimeout,
	CheckRedirect: func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	},
}

type vanityURLLookupLockKey struct{}

// ContextWithVanityURLLookupLock makes an explicitly loaded workspace lock
// available while resolving module sources for a workspace overlay.
func ContextWithVanityURLLookupLock(ctx context.Context, lock *workspace.Lock) context.Context {
	return context.WithValue(ctx, vanityURLLookupLockKey{}, lock)
}

// ResolveDaggerGetRedirect resolves a dagger-get vanity URL for any Git-backed
// source consumer, including both modules and workspaces. It first consults the
// workspace lockfile, then falls back to the session-cached HTTP probe.
func ResolveDaggerGetRedirect(ctx context.Context, refString string) (string, error) {
	if !daggerGetEligible(refString) {
		return refString, nil
	}

	sourceURL, version, err := splitSourceURLVersion(refString)
	if err != nil {
		return refString, nil //nolint:nilerr // deliberate: unparseable refs fall back to the original ref
	}

	lock, lockOverridden := ctx.Value(vanityURLLookupLockKey{}).(*workspace.Lock)
	var setLookup func(string, string, []any, string) error
	query, queryErr := CurrentQuery(ctx)
	if lockOverridden {
		setLookup = lock.SetLookup
	} else if queryErr == nil {
		var ok bool
		lock, ok, err = query.CurrentWorkspaceLock(ctx, false)
		if err != nil {
			return "", fmt.Errorf("vanity-url lockfile: %w", err)
		}
		if !ok {
			lock = nil
		}
	}

	lockInputs := []any{sourceURL}
	if lock != nil {
		if resolvedURL, ok := lock.GetLookup(
			workspace.CoreLockNamespace,
			workspace.LockOperationVanityURL,
			lockInputs,
		); ok {
			return sourceURLWithVersion(resolvedURL, version), nil
		}
		// Keep legacy entries authoritative: an older engine can ignore a new
		// identity entry and subsequently discover a redirect of its own.
		if resolvedURL, ok := lock.GetLookup(
			workspace.CoreLockNamespace,
			workspace.LockOperationVanityURLResolution,
			lockInputs,
		); ok {
			if resolvedURL == sourceURL {
				// A schemeless source still needs transport selection; #ref:subpath
				// and @version are also distinct selectors, not interchangeable.
				return refString, nil
			}
			return sourceURLWithVersion(resolvedURL, version), nil
		}
		if !lockOverridden && queryErr == nil {
			_, lockWritable, err := query.CurrentWorkspaceLock(ctx, true)
			if err != nil {
				return "", fmt.Errorf("vanity-url lockfile: %w", err)
			}
			if lockWritable {
				setLookup = func(namespace, operation string, inputs []any, value string) error {
					return query.SetCurrentWorkspaceLookup(ctx, namespace, operation, inputs, value)
				}
			}
		}
	}

	cache, cacheErr := dagql.EngineCache(ctx)
	clientMetadata, mdErr := engine.ClientMetadataFromContext(ctx)
	if cacheErr != nil || mdErr != nil {
		return refString, nil //nolint:nilerr // deliberate: no session infrastructure means no probe, keep parsing network-free
	}

	res, err := cache.GetOrInitArbitrary(
		ctx,
		clientMetadata.SessionID,
		// Scope the cached value to the session: GetOrInitArbitrary looks entries
		// up by call key alone (the session ID only tracks ownership), so the
		// session ID must be part of the key to keep results session-private.
		"module-dagger-get-redirect:"+clientMetadata.SessionID+":"+sourceURL,
		func(ctx context.Context) (any, error) {
			return daggerGetProbeResolution(ctx, sourceURL), nil
		},
	)
	resolution := daggerGetResolution{ref: sourceURL}
	if err != nil {
		slog.Debug("dagger-get redirect cache error; probing directly", "ref", refString, "error", err)
		resolution = daggerGetProbeResolution(ctx, sourceURL)
	} else if resolved, ok := res.Value().(daggerGetResolution); ok && resolved.ref != "" {
		resolution = resolved
	}

	if resolution.ref == sourceURL {
		if resolution.noRedirect && setLookup != nil && canRecordVanityIdentity(sourceURL) {
			// An HTTP 200 records only URL routing, not Git visibility or caller
			// authorization. Errors and ignored redirects remain session-local.
			if err := setLookup(workspace.CoreLockNamespace, workspace.LockOperationVanityURLResolution, lockInputs, sourceURL); err != nil {
				return "", fmt.Errorf("set vanity-url-resolution lock entry: %w", err)
			}
		}
		return refString, nil
	}
	if setLookup == nil {
		return sourceURLWithVersion(resolution.ref, version), nil
	}
	// Store the destination before applying the caller's version. A version in
	// the redirect is its default and must survive later lookups and refreshes.
	if err := setLookup(
		workspace.CoreLockNamespace,
		workspace.LockOperationVanityURL,
		lockInputs,
		resolution.ref,
	); err != nil {
		return "", fmt.Errorf("set vanity-url lock entry: %w", err)
	}
	return sourceURLWithVersion(resolution.ref, version), nil
}

func canRecordVanityIdentity(sourceURL string) bool {
	u, err := url.Parse(sourceURL)
	// A routing observation must not newly copy inline credentials or query
	// tokens into an automatically exported, normally committed lockfile.
	// Keep the full session-local key; stripping secrets could merge inputs.
	return err == nil && u.User == nil && u.RawQuery == ""
}

func splitSourceURLVersion(refString string) (string, string, error) {
	normalized := strings.Replace(refString, "#", "@", 1)
	if !strings.HasPrefix(normalized, gitref.SchemeHTTPS.Prefix()) {
		normalized = gitref.SchemeHTTPS.Prefix() + normalized
	}
	u, err := url.Parse(normalized)
	if err != nil {
		return "", "", err
	}
	version := ""
	if i := strings.Index(u.Path, "@"); i >= 0 {
		version = u.Path[i+1:]
		u.Path = u.Path[:i]
	}
	// Keep the scheme so schemeless and HTTPS refs share one lockfile key.
	return u.String(), version, nil
}

func sourceURLWithVersion(sourceURL, version string) string {
	if version == "" {
		return sourceURL
	}
	schemeless := !strings.HasPrefix(sourceURL, gitref.SchemeHTTPS.Prefix())
	parsedURL := sourceURL
	if schemeless {
		parsedURL = gitref.SchemeHTTPS.Prefix() + parsedURL
	}
	u, err := url.Parse(parsedURL)
	if err != nil {
		return sourceURL + "@" + version
	}
	// An explicit caller version overrides a default supplied by the redirect.
	u.Fragment = ""
	if i := strings.Index(u.Path, "@"); i >= 0 {
		u.Path = u.Path[:i]
	}
	u.Path = strings.TrimSuffix(u.Path, "/") + "@" + version
	resolved := u.String()
	if schemeless {
		resolved = strings.TrimPrefix(resolved, gitref.SchemeHTTPS.Prefix())
	}
	return resolved
}

// daggerGetEligible reports whether the redirect probe applies to refString.
// Only https and schemeless refs qualify; local paths, SCP-like refs, and
// explicit non-https schemes (http, ssh, git) are excluded.
func daggerGetEligible(refString string) bool {
	if refString == "" || refString[0] == '/' || refString[0] == '.' {
		return false
	}
	if strings.Contains(refString, "://") && !strings.HasPrefix(refString, gitref.SchemeHTTPS.Prefix()) {
		return false
	}
	switch gitref.Scheme(refString) {
	case gitref.SchemeHTTPS:
		return true
	case gitref.NoScheme:
		// Schemeless refs are attempted over https; require a hostname with a
		// dot so we don't probe obvious non-URLs.
		host := refString
		if i := strings.IndexAny(host, "/@:"); i >= 0 {
			host = host[:i]
		}
		return strings.Contains(host, ".")
	default:
		return false
	}
}

// daggerGetProbe performs the actual single-hop redirect probe and returns the
// resolved ref, or the original ref on any non-redirect outcome.
func daggerGetProbe(ctx context.Context, refString string) string {
	return daggerGetProbeResolution(ctx, refString).ref
}

type daggerGetResolution struct {
	ref string
	// noRedirect means an HTTP 200 was observed, not merely that we fell back
	// to the original ref after an error or ignored redirect. This observation
	// may be pinned until explicit update; it says nothing about Git access.
	noRedirect bool
}

func daggerGetProbeResolution(ctx context.Context, refString string) daggerGetResolution {
	fallback := daggerGetResolution{ref: refString}
	// Module refs spell versions with "@" (and historically "#"); normalize so
	// url.Parse doesn't treat a version as a URL fragment.
	normalized := strings.Replace(refString, "#", "@", 1)
	if !strings.HasPrefix(normalized, gitref.SchemeHTTPS.Prefix()) {
		normalized = gitref.SchemeHTTPS.Prefix() + normalized
	}

	u, err := url.Parse(normalized)
	if err != nil {
		return fallback
	}

	// Strip a path-level "@version"; userinfo "@" stays in u.User, not u.Path.
	version := ""
	if i := strings.Index(u.Path, "@"); i >= 0 {
		version = u.Path[i+1:]
		u.Path = u.Path[:i]
	}

	probe := *u
	probe.RawQuery = daggerGetQueryParam + "=1"
	probe.Fragment = ""

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, probe.String(), nil)
	if err != nil {
		return fallback
	}
	resp, err := daggerGetClient.Do(req)
	if err != nil {
		slog.Debug("dagger-get probe failed; using original ref", "url", probe.String(), "error", err)
		return fallback
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusMultipleChoices || resp.StatusCode >= http.StatusBadRequest {
		fallback.noRedirect = resp.StatusCode == http.StatusOK
		return fallback
	}

	loc := resp.Header.Get("Location")
	if loc == "" {
		return fallback
	}
	locURL, err := url.Parse(loc)
	if err != nil || locURL.Scheme != "https" || locURL.Host == "" {
		slog.Debug("dagger-get redirect ignored: Location is not an absolute https URL",
			"ref", refString, "location", loc)
		return fallback
	}

	// Hosts also emit incidental 3xx responses that are not dagger-get
	// opt-ins: auth walls (e.g. GitLab 302s unauthenticated repo paths to
	// /users/sign_in, dropping the query string) and same-repo URL
	// canonicalization. Require the Location to echo the dagger-get marker as
	// proof of intent: a host opting in preserves the query (standard
	// path+query passthrough redirects do), while auth-wall redirects drop it.
	if locURL.Query().Get(daggerGetQueryParam) != "1" {
		slog.Debug("dagger-get redirect ignored: Location does not echo the dagger-get marker",
			"ref", refString, "location", loc)
		return fallback
	}

	// Canonicalization redirects (e.g. GitHub 301s "repo.git" -> "repo",
	// "www." -> apex, trailing-slash and case fixups) echo the query string,
	// so they pass the marker check above. Treating them as redirects would
	// silently rewrite the user's ref and change the module's clone
	// ref/identity. Only honor redirects that point somewhere genuinely
	// different.
	if canonicalRepoKey(u) == canonicalRepoKey(locURL) {
		slog.Debug("dagger-get redirect ignored: same-repo canonicalization",
			"ref", refString, "location", loc)
		return fallback
	}

	// Drop only the dagger-get param the server may have echoed back.
	q := locURL.Query()
	q.Del(daggerGetQueryParam)
	locURL.RawQuery = q.Encode()

	resolved := sourceURLWithVersion(locURL.String(), version)
	slog.Debug("dagger-get redirect resolved", "from", refString, "to", resolved)
	return daggerGetResolution{ref: resolved}
}

// canonicalRepoKey reduces a URL to a host+path key that is stable across the
// common canonicalization redirects hosts emit for the same repository:
// case-only differences, a leading "www.", a ".git" suffix, and trailing
// slashes.
func canonicalRepoKey(u *url.URL) string {
	host := strings.ToLower(u.Host)
	host = strings.TrimPrefix(host, "www.")
	path := strings.ToLower(u.Path)
	path = strings.TrimSuffix(path, "/")
	path = strings.TrimSuffix(path, ".git")
	return host + path
}
