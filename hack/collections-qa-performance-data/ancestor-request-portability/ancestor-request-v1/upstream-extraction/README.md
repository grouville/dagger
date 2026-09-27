# Scope of the extracted patch

The original extraction contains six production files and three focused test files. `manifest.json` records exact source hashes, and the original patch passed `git apply --check` before the parent applied it. It contains the useful fixed-label `filesync.syncParentDirs` wcprof marker by request; the same marker was present in both measured engines.

Production paths: engine/opts.go, engine/parent_directory_request.go, engine/filesync/filesyncer.go, engine/filesync/remotefs.go, engine/client/filesync.go, internal/fsutil/parent_metadata.go. Tests: engine/parent_directory_request_test.go, engine/client/filesync_parent_metadata_test.go, internal/fsutil/parent_metadata_test.go.

This exact v1 extraction has been superseded for upstream adoption by the v2 portable root predicate in `ancestor-request-v2/portable-correction.patch`, and then the v3 normalized-mode test oracle in `ancestor-request-v3/test-oracle.patch`. Preserve those separate provenance steps. V1 remains the exact measured Linux source. V2 has identical production behavior on Linux and fixes the Windows protocol root; v3 changes only a test oracle.

No SDK, Dang, schema, telemetry, module source, dependency, engine image or fixture change is part of this patch. Those frozen inputs define the controlled benchmark stack, not the proposed upstream scope. No static host snapshot cache or new result-cache identity is introduced.
