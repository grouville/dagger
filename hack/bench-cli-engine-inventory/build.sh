#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
perf_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
perf_owner=/tmp/dagger-container-inventory.NMh2Z3QV
perf_flags='-s -w -X github.com/dagger/dagger/engine.Tag=350e22edd -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCS=git -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSRevision=350e22edd -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSModified=true'
cd "$perf_owner/source"
git diff --check
sha256sum go.mod go.sum engine/client/drivers/container.go engine/client/drivers/docker.go engine/client/drivers/apple.go engine/client/drivers/container_create_test.go engine/client/drivers/container_test.go engine/client/drivers/container_inventory_test.go engine/client/drivers/container_inventory_docker_test.go > "$perf_owner/build-inputs.sha256"
# DRIVER_TEST-gated runtime integration suites are deliberately not enabled:
# their old shared names/image cleanup are unsafe on this shared machine.
unset DRIVER_TEST
"$perf_go" test -mod=readonly -race -count=3 ./engine/client/drivers > "$perf_owner/after-contract-unit.log" 2>&1
"$perf_go" build -mod=readonly -buildvcs=false -trimpath -ldflags="$perf_flags" -o "$perf_owner/dagger-candidate" ./cmd/dagger
sha256sum --check "$perf_owner/build-inputs.sha256"
"$perf_go" version -m "$perf_owner/dagger-candidate"
sha256sum "$perf_owner/dagger-candidate"
