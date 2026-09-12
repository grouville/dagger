#!/usr/bin/env bash
set -euxo pipefail
cd /tmp/dagger-http-preconnect-main.tRLouH4d/source
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
perf_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
perf_owner=/tmp/dagger-http-preconnect-main.tRLouH4d
perf_flags='-s -w -X github.com/dagger/dagger/engine.Tag=350e22edd -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCS=git -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSRevision=350e22edd -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSModified=true'
"$perf_go" version
git rev-parse HEAD
git diff --check
sha256sum engine/client/client.go engine/client/http_preconnect.go engine/client/http_preconnect_test.go go.mod go.sum "$perf_owner/control-client.go" "$perf_owner/control-overlay.json" > "$perf_owner/build-inputs.sha256"
"$perf_go" build -mod=readonly -buildvcs=false -trimpath -overlay="$perf_owner/control-overlay.json" -ldflags="$perf_flags" -o "$perf_owner/dagger-control" ./cmd/dagger
"$perf_go" build -mod=readonly -buildvcs=false -trimpath -ldflags="$perf_flags" -o "$perf_owner/dagger-candidate" ./cmd/dagger
sha256sum --check "$perf_owner/build-inputs.sha256"
sha256sum "$perf_owner/dagger-control" "$perf_owner/dagger-candidate" > "$perf_owner/binaries.sha256"
"$perf_go" version -m "$perf_owner/dagger-control"
"$perf_go" version -m "$perf_owner/dagger-candidate"
