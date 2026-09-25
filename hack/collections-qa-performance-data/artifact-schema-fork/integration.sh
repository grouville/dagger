#!/bin/bash
set -eu
docker start dagger-engine.collections-artifact-schema-fork > /tmp/collections-perf/discovery-next/restart-integration.log
cd /home/dagger/dag/core/integration
env -u SSH_AUTH_SOCK \
 DAGGER_ENGINE=container://dagger-engine.collections-artifact-schema-fork \
 _EXPERIMENTAL_DAGGER_RUNNER_HOST=container://dagger-engine.collections-artifact-schema-fork \
 _EXPERIMENTAL_DAGGER_CLI_BIN=/tmp/collections-perf/committed/dagger \
 DAGGER_SRC_ROOT=/home/dagger/dag \
 /tmp/collections-perf/half-second/integration.test \
 -test.run '^Test(Artifacts|Collections)/(TestValueAfterDiscoveringSessionEnds|TestWorkspaceEdits|TestModuleBoundary|TestCoreSelection|TestCheckCachePolicy|TestExplicitEntrypoint|TestCommandListSchemaPaths|TestBatchReplacement|TestCheckSelection|TestEnumKeys)$' \
 -test.parallel=1 -test.timeout=10m -test.v > /tmp/collections-perf/discovery-next/integration.log 2>&1
