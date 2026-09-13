#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
export DAGGER_TEST_DOCKER_INVENTORY=1
export DAGGER_TEST_INVENTORY_IMAGE=rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b
perf_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
cd /tmp/dagger-container-inventory.NMh2Z3QV/source
"$perf_go" test -mod=readonly -race -count=1 -run '^TestDockerContainerInventoryContract$' -v ./engine/client/drivers > /tmp/dagger-container-inventory.NMh2Z3QV/docker-contract.log 2>&1
