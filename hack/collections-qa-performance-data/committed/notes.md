# Committed performance stack

The build at dagger `6e6bdfb16a` includes seven new focused code commits and the
original commits from performance PRs #14180, #14182, #14183, and #14179.
Benchmark tooling was committed separately as `a8ee0d74ae` after this build;
that changes no engine or CLI source.

Go scanner commit: `c84f15b11981bdc2eb52987d4e6139c4309bfd82` on
`perf/scanner-index` in `/tmp/dagger-go-discovery`.
Dang map commit: `d7fadb86cb93a0225fe6e3e699e995fd49cfede6` on
`perf/collections-map-merge` in `/tmp/dang-collections-upstream`.
The map fix is independent and is not consumed by this engine build. Dagger
continues to depend on the released `github.com/vito/dang/v2 v2.1.4`.

The Go scanner walks an immutable input snapshot with filepath.WalkDir,
associates files with their nearest module, and caches each module's parsed
comment directives inside that scanner process. It uses go/parser for the
existing directive analysis and golang.org/x/mod/modfile for go.mod. Test names
are extracted by a compatibility regular expression over bytes already read.
It writes .testnames alongside the existing scan output. The original module
instead asks for directories, globs each directory, calls workspace search
(ripgrep), transports matches, and filters all matches for each file.

This is removal of a redundant pass and an O(files * matches) join, not proof
that a Go regexp or go/parser beats ripgrep in isolation. Name ordering,
duplicate handling, ignored directories, build-tag behavior, and the original
single-line declaration rules are preserved. Every changed immutable snapshot
still participates in the ordinary Dagger exec cache key.

No experimental AST reflection clone, local Go module replacement, prebuilt
scanner, native-Git telemetry rewrite, TypeScript instrumentation, or direct
library API experiment is in the engine/module commits.

These are local review commits; nothing has been pushed. The two sibling
repository commits are unsigned because their configured SSH signer was
unavailable. Signing configuration was not changed.
