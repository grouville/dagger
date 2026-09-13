#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off GOSUMDB=off
export GOMODCACHE=/home/dagger/go/pkg/mod
export GOCACHE=/tmp/dagger-client-dial-f1d6824-draft-TGRdXA/go-build-cache
stats_root=/tmp/dagger-parser-patch-repro.LtDo8kx6
stats_evidence=/tmp/dagger-parser-stats.I2WPGLrS/publish/hack/bench-parser-choice-statistics
stats_go=/tmp/dagger-rust-cli-toolchain.eFwaZS/mod/golang.org/toolchain@v0.0.1-go1.26.8.linux-amd64/bin/go
export PATH="$(dirname "$stats_go"):$PATH"
test ! -e "$stats_root/pigeon"
test ! -e "$stats_root/dang"
cp -a /tmp/dagger-parser-stats.I2WPGLrS/download-cache/github.com/mna/pigeon@v1.3.1-0.20260627070130-aa1e61c16975 "$stats_root/pigeon"
cp -a /home/dagger/go/pkg/mod/github.com/vito/dang/v2@v2.1.3 "$stats_root/dang"
chmod -R u+w /tmp/dagger-parser-patch-repro.LtDo8kx6/pigeon /tmp/dagger-parser-patch-repro.LtDo8kx6/dang
git -C "$stats_root/pigeon" init -q
git -C "$stats_root/dang" init -q
cd "$stats_root/pigeon"
git apply --check "$stats_evidence/patches/pigeon.patch"
git apply "$stats_evidence/patches/pigeon.patch"
(cd builder && "$stats_go" generate static_code.go)
cmp builder/generated_static_code.go /tmp/dagger-parser-stats.I2WPGLrS/pigeon/builder/generated_static_code.go
"$stats_go" build -mod=readonly -buildvcs=false -o "$stats_root/pigeon-candidate" .
"$stats_root/pigeon-candidate" -nolint -o examples/json/json.go examples/json/json.peg
"$stats_root/pigeon-candidate" -nolint -optimize-parser -optimize-basic-latin -o examples/json/optimized/json.go examples/json/json.peg
"$stats_root/pigeon-candidate" -nolint -optimize-grammar -o examples/json/optimized-grammar/json.go examples/json/json.peg
"$stats_go" test -mod=readonly -buildvcs=false -race -count=1 -timeout=3m ./examples/json -run '^TestChoice' -v
cd "$stats_root/dang/pkg/dang"
"$stats_root/pigeon-candidate" -support-left-recursion -o dang.peg.go dang.peg
cmp dang.peg.go /tmp/dagger-parser-stats.I2WPGLrS/dang/pkg/dang/dang.peg.go
cp "$stats_evidence/patches/dang-choice-statistics_test.go.txt" choice_statistics_test.go
export DAGGER_RUST_PARSE_FIXTURE="$stats_evidence/fixtures/rust-module.dang"
cd "$stats_root/dang"
"$stats_go" test -mod=readonly -buildvcs=false -race -count=1 -timeout=3m ./pkg/dang -run '^TestChoiceStatistics' -v
# One iteration proves the relocated benchmark reads the published input. This
# single iteration is not a performance measurement.
"$stats_go" test -mod=readonly -buildvcs=false -count=1 ./pkg/dang -run '^$' \
  -bench='^BenchmarkRustModuleParseChoiceStatistics$/^counted=false$' -benchtime=1x
