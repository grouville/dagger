#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
stats_owner=/tmp/dagger-parser-stats.I2WPGLrS
stats_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
cd "$stats_owner/pigeon"
"$stats_owner/pigeon-candidate" -nolint -o examples/json/json.go examples/json/json.peg
"$stats_owner/pigeon-candidate" -nolint -optimize-parser -optimize-basic-latin -o examples/json/optimized/json.go examples/json/json.peg
"$stats_owner/pigeon-candidate" -nolint -optimize-grammar -o examples/json/optimized-grammar/json.go examples/json/json.peg
"$stats_owner/pigeon-candidate" -nolint -support-left-recursion -o test/left_recursion/standart/leftrecursion/left_recursion.go test/left_recursion/left_recursion.peg
"$stats_owner/pigeon-candidate" -nolint -optimize-parser -support-left-recursion -o test/left_recursion/optimized/leftrecursion/left_recursion.go test/left_recursion/left_recursion.peg
"$stats_owner/pigeon-candidate" -nolint -o test/left_recursion/standart/withoutleftrecursion/without_left_recursion.go test/left_recursion/without_left_recursion.peg
"$stats_owner/pigeon-candidate" -nolint -optimize-parser -o test/left_recursion/optimized/withoutleftrecursion/without_left_recursion.go test/left_recursion/without_left_recursion.peg
"$stats_go" test -mod=readonly -buildvcs=false -race -count=3 -timeout=3m ./builder ./examples/json ./test/left_recursion > "$stats_owner/pigeon-tests.log" 2>&1
cd "$stats_owner/dang"
"$stats_go" test -mod=readonly -buildvcs=false -race -count=3 -timeout=3m ./pkg/dang -run '^TestChoiceStatistics' -v > "$stats_owner/dang-race-tests.log" 2>&1
"$stats_go" test -mod=readonly -buildvcs=false -c -o "$stats_owner/dang-control.test" -overlay="$stats_owner/control-overlay.json" ./pkg/dang
"$stats_go" test -mod=readonly -buildvcs=false -c -o "$stats_owner/dang-candidate.test" ./pkg/dang
sha256sum "$stats_owner/dang-control.test" "$stats_owner/dang-candidate.test" "$stats_owner/control.dang.peg.go" pkg/dang/dang.peg.go pkg/dang/choice_statistics_test.go > "$stats_owner/parse-bench-inputs.sha256"
python3 "$stats_owner/bench.py"
