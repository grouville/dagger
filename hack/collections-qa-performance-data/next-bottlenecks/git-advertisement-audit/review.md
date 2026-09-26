# Git module-load latency: read-only audit

The saved Kyle expanded-list profile has **702.6 ms of aggregate anonymous Git advertisement work**, overlapping in **one 320.4 ms interval**, from 16.7 to 337.0 ms of a 1.230 s engine trace. There are seven actual probe operations. Their starts occur in dependency-loading waves near 17, 83, 177 and 255 ms. This is neither 703 ms of CLI savings nor an additional CPU cost to add to overlapping SDK/runtime spans. The saved what-if/end-path model does not establish the critical-path saving for this class.

`GitRef.tree` is already cheap in this capture (10 recorded operations, 1.85 ms aggregate); there is no `git.lsRemote` operation. The existing session advertisement reuse is doing its intended work: do not reintroduce a second Git process/HTTP refs lookup while changing visibility handling. Exact intervals are in saved-profile-git-summary.json. Counts combine the existing wcprof event types as noted in the raw profile; the seven advertisement events themselves are unique internal operations.

## What must remain authoritative

The HTTP `Query.git` constructor first determines whether it may consult implicit caller credentials. Arbitrary nested module runtime requests cannot use the host credential helper; trusted dependency/SDK loading may fall back to the originating caller. The anonymous probe then chooses an anonymous identity or an explicit secret-bearing identity before `__gitRepository` constructs the reusable object. Sources: core/schema/git.go:863–1029 and core/modulesource.go:2123–2138.

The current probe is session-scoped, keyed by the remote URL and session. A service-bound remote bypasses this shared answer. `PrimePublicRemote` refuses credentialed, user-info, SSH and service-bound lookups; it seeds only the existing session metadata cache. Tests explicitly require a new session to observe a public→private transition. Preserve these properties; a commit SHA, workspace pin, cached checkout, or distributed-cache hit is not a new authorization grant.

The synchronous placement is a design choice rather than an intrinsic requirement of parsing artifact names. However, moving it after cached-source/schema access needs an explicit authority model: private cached source cannot be used to discover which credentials it would need. A lazy credential-source recipe must resolve trusted caller authority before both cache reuse and any network operation; simply skipping the probe for a pin is not that design. There is already a narrow `gitRemoteHasWorkspacePin` fallback on probe **errors**, but a 401/public=false response still selects credentials. Do not silently broaden that exception into a global visibility cache.

## Already-shared transport; no known fresh-client bug

`publicRemoteAdvertisement` is go-git HTTP, not a Git subprocess (core/schema/git_visibility.go:21). `client.NewClient` looks up a registered transport. Dagger registers an injectable wrapper over `http.DefaultTransport` once (core/schema/git.go:37); for ordinary URLs the go-git session clones only the lightweight `http.Client`, retaining the same RoundTripper. Its session Close is a no-op. The DNS wrapper forwards to that same transport; with no service DNS configuration it uses the default resolver and does not clone the transport.

Thus new TCP/TLS handshakes per repository are not proved by these spans. Need actual GotConn/Reused, DNS, connect, TLS, HTTP version and TTFB counters. For HTTP/1, also check whether advertisement parsing stops at the Git flush packet before HTTP EOF, and whether the response is chunked or has a Content-Length: go-git closes the body after parsing, without a general drain. That is a hypothesis for connection reuse, not a measured regression. A local gated HTTP/1 server can establish it without hitting a remote registry or Cloud. HTTP/2 behaves differently; do not apply an unbounded drain to arbitrary servers.

## Additional concrete lead: vanity URL probes before Git

`ResolveDaggerGetRedirect` runs before `ParseGitRefString` (core/modulerefs.go:70,97). `daggerGetEligible` intentionally includes **all HTTPS and schemeless hosts**, with an explicit test that `github.com/dagger/dagger` is eligible (core/modulerefs_redirect_test.go:24). A positive redirect uses a workspace `vanity-url` lock entry. A non-redirect response is stored only in the session cache; the next CLI session performs `GET …?dagger-get=1` again. `daggerGetProbe` closes the response without reading its body. This can be a whole HTML page for an ordinary Git hosting URL.

Three advertisement operations begin ~68–72 ms after their parent `Query.moduleSource` begins, while others start in ~1–3 ms. The report attributes 555.5 ms aggregate self-time to moduleSource, but has no vanity-HTTP boundary. This is consistent with additional source-resolution HTTP, **not proof** of its cost. Instrument this before optimizing only the 83 ms Git calls.

A negative/self source-resolution lock could remove repeated vanity discovery while preserving fresh Git authority checks, but it is a deliberate lock/update contract change. The current probe returns the original ref on both non-redirect HTTP and transient network/parse errors: never persist that undifferentiated fallback as a negative result. A proper result must distinguish validated “no redirect” from unavailable/invalid responses, specify `dagger update` refresh semantics, and preserve redirect/default-version behavior. Hardcoding github.com as exempt changes the currently tested contract and should not be slipped in as a transparent optimization.

## Smallest useful next experiment

1. Add diagnostic-only spans/counters around `daggerGetProbe` and the existing advertisement: session-cache/lock hit category, anonymous URL hash, body bytes, ref count, HTTP status class and redirect count; use net/http/httptrace for connection reuse, DNS, connect, TLS, wrote-request→first-byte and total-body durations. Do not record tokens, response bodies or credential contents. Separate AllReferences validation and remote conversion time if ref counts are large.
2. Capture one normal cold-engine command, two unchanged warm commands, and one ordinary source edit plus the same command. These are profiling captures, not enough observations for a wall-time speedup claim. This distinguishes an empty Dagger volume, a fresh HTTP pool, and the per-new-session authority/vanity costs.
3. Choose **one** candidate from the observed phase. If connection setup repeats, first reproduce it with local HTTP/1 and HTTP/2 servers and fix pooling/limited draining only when safe. If TTFB dominates, changing clients will not remove that RTT. If negative vanity discovery dominates, prototype an explicit source-resolution lock result with correct refresh/failure semantics, then use matched warm/edit pairs. If dependency waves dominate, prepare only already-required direct dependencies early and let the existing session singleflight serve the later loads; preserve cancellation and avoid probing all unused lock entries.
4. Keep anonymous-public→private across sessions, credential rotation, nested unauthorized vs trusted dependency callers, service DNS separation, offline pinned source behavior, HEAD/tag/peeled refs, redirect/default-version updates, cancellation and source output parity as correctness gates.

A pinned-only lightweight Git protocol-v2 capabilities probe could reduce O(number-of-refs) response/parse work on huge repositories, while ordinary ref resolution retains full advertisements. That is a secondary protocol/provider compatibility experiment, not the first fix: the present profile has no ref-count/body-size evidence, and it can trade a single useful advertisement for another round trip when refs are needed.

## PR overlap checked from current open list

The query returned 73 open PRs. Relevant current descriptions/file lists were read directly with gh; no source changes or runtime calls were made for this audit.

- [#14145, Marcos: reuse dependencies for CurrentModule source APIs](https://github.com/dagger/dagger/pull/14145): directly removes redundant dependency re-resolution and its network/auth work for an already-running module. Reuse it rather than duplicate its `preloadedDeps` path. Its documented client-generator resolution follow-up is related. It does not remove the first per-session visibility probe for a required remote.
- [#14299, Yves / eunomie: key module calls on declared clients and Git commit](https://github.com/dagger/dagger/pull/14299): cache correctness for local declared clients and sibling modules at a Git commit; can intentionally invalidate results. No HTTP advertisement/pool change. Preserve its broader identity if making source loading earlier/lazier.
- [#14167, Vito: release mirrors before checkout](https://github.com/dagger/dagger/pull/14167): shortens mirror-lock ownership around materialization/submodules. It matters for real cold checkouts; the anonymous HTTP visibility path does not acquire that mirror lock.
- [#14314, Vito: accelerate agent workspace commits](https://github.com/dagger/dagger/pull/14314): Git-native transaction/incremental checkout work; supporting no-fetch/history changes. It is not a fix for these seven anonymous HTTP probes.
- [#14213, Tibor: upload-pack workspace sync](https://github.com/dagger/dagger/pull/14213): host workspace transfer and source materialization; no replacement for remote module visibility/source-resolution calls.

The branch already contains `5e487bc94c` (reuse public Git advertisements within a session). No current open PR title/file scope examined establishes that the remaining vanity/probe RTT problem is already solved; this is a scoped audit, not a claim that no other branch contains related work.

## Diagnostic overlay prepared after review

`vanity-overlay.json` replaces only core/modulerefs_redirect.go. `vanity-profiling.patch` is the portable diff; `vanity-manifest.json` records base/overlay hashes. It is formatted but **uncompiled and unrun**. No shared files changed.

New wcprof classes are fixed strings: `module.resolveDaggerGetRedirect`, `module.daggerGetProbe`, and external-I/O `module.daggerGetHTTP` (HTTP request through response headers; the parent includes response closure). New internal OTel attributes are finite decision labels and numeric status only. No source URL, host, ref, query, token or response body is added. Instrumented errors use generic text rather than a net/url error that could embed the URL. Existing return values, lock behavior, redirects and source errors remain unchanged. The diagnostic adds spans, so its wall time must not be presented as an optimization result.

Resolution labels distinguish ineligible, invalid input, no session infrastructure, positive lock hit, session hit/miss, cache failure/fallback and unexpected cache value. Probe labels distinguish actual redirect, HTTP non-redirect, missing/invalid location, missing opt-in marker, same-repository canonicalization, malformed request, and transport failure. A 4xx/5xx response remains identifiable by its status code even though current behavior deliberately falls back without a returned error.

Suggested local-only focused compile/test after a slot is granted: existing `TestDaggerGet*`, `TestResolveDaggerGetRedirect*`, and vanity lock-update tests. No test or engine run was performed by this audit.

## Why existing Git pins do not prove source-resolution identity

A `git-latest` entry identifies normalized repository + selector options → ref; `git-sha` identifies normalized repository + ref → commit. `normalizeLookupInputs` deliberately erases the transport distinction. Neither entry stores the original module source URL, module subpath, or whether its HTTPS vanity endpoint opted into a redirect. The only source-mapping evidence is `vanity-url(sourceURL) → destination`, which already bypasses HTTP.

Counterexample: a workspace has a valid Git pin for repository A from an SSH/API Git call. A later module source uses the HTTPS URL spelling of A, whose HTTP vanity endpoint intentionally redirects to repository B. Current behavior consults vanity resolution first and selects B. Treating the existing Git pin as proof that this module source is direct Git would silently choose A instead. Even for a source used previously, negative redirect results are currently refreshed in new sessions; Git pins alone cannot establish the missing negative observation.

The merged [#14037 contract](https://github.com/dagger/dagger/pull/14037) explicitly makes eligibility universal for HTTPS/schemeless module/workspace sources, pins positive mappings, and requires updates of existing positive mappings to fail if the redirect disappears. So negative-lock persistence is a source-resolution contract extension that needs review, not an existing-pin shortcut. A narrower internal bypass could be sound when a caller already holds a resolved source object or explicit positive source mapping with current authority; preserve that provenance instead of inferring it from any Git lock entry. Reuse of already-loaded dependency objects overlaps #14145 and should build on it.
