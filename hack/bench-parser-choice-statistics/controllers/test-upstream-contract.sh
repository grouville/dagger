#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
stats_owner=/tmp/dagger-parser-stats.I2WPGLrS
stats_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
cd "$stats_owner/pigeon"
"$stats_go" test -mod=readonly -buildvcs=false -race -count=10 -timeout=3m ./examples/json \
  -run '^TestChoice' -v > "$stats_owner/pigeon-contract-candidate.log" 2>&1
set +e
"$stats_go" test -mod=readonly -buildvcs=false -count=1 -timeout=1m \
  -overlay="$stats_owner/pigeon-contract-control-overlay.json" ./examples/json \
  -run '^TestChoiceStatistics(Default|Restore)$' -v > "$stats_owner/pigeon-contract-control.log" 2>&1
stats_status=$?
set -e
test "$stats_status" -eq 1
rg -q 'default statistics must retain expression counting without choice counters' "$stats_owner/pigeon-contract-control.log"
rg -q 'undo must restore the exact disabled state' "$stats_owner/pigeon-contract-control.log"
rg -q '^--- FAIL: TestChoiceStatisticsDefault' "$stats_owner/pigeon-contract-control.log"
rg -q '^--- FAIL: TestChoiceStatisticsRestore' "$stats_owner/pigeon-contract-control.log"
