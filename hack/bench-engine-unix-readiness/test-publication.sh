#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
perf_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
cd /tmp/dagger-unix-readiness-publish.a8gBlRgK/repo
sha256sum cmd/dialstdio/main.go cmd/dialstdio/main_test.go cmd/dialstdio/stdio_test.go go.mod go.sum > /tmp/dagger-unix-readiness-publish.a8gBlRgK/publication-inputs.sha256
"$perf_go" test -mod=readonly -race -count=3 -timeout=90s -run '^TestDial' ./cmd/dialstdio > /tmp/dagger-unix-readiness-publish.a8gBlRgK/publication.log 2>&1
