# Snapshot-derived Go test directories

[Results and limits](../../NATIVE_GO_TEST_DIRECTORY_DISCOVERY.md): 24 successful timing commands, seven focused checks and two diagnostic captures. Warm test-edit median 12.22 → 11.25 seconds; ordinary-source listing flat. Cold effects are unmeasured.

`evidence.tar.gz` includes baseline and candidate module archives, the minimal patch, drivers, all outputs, golden rows, CPU/allocation/pressure counters, checks, restoration records, final engine identities, wcprof chunks and CPU profiles. `summary.json` gives comparisons; `manifest.json` hashes each member and `archive.json` identifies the verified archive. Binaries and duplicate uncompressed wcprof streams are excluded.

After unpacking, `python3 reconstruct.py capture-before` and `python3 reconstruct.py capture-candidate` reconstruct recordings, checking their epoch, string tables, zero drops and closed operations. `analyze.py` preserves count and critical-path analysis and requires the diagnostic wcprof reporter. Drivers retain their original `/tmp` paths; their shared protocol is included as `common-protocol.py`. Use the recorded identities and preceding [discovery-screen stack](../go-discovery-screens/) to recreate the environment.

This module branch includes the earlier experimental snapshot API. It is prepared for fork review, not a standalone upstream PR.
