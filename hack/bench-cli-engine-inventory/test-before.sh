#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
perf_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
cd /tmp/dagger-container-inventory.NMh2Z3QV/source
sha256sum engine/client/drivers/container.go engine/client/drivers/docker.go engine/client/drivers/apple.go engine/client/drivers/container_inventory_test.go > /tmp/dagger-container-inventory.NMh2Z3QV/before-inputs.sha256
"$perf_go" test -mod=readonly -race -count=3 -run '^TestContainerInventoryPrefilterCommands$' ./engine/client/drivers > /tmp/dagger-container-inventory.NMh2Z3QV/before.log 2>&1
