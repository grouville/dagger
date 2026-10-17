# restored-postings-removal

A linear imported-membership removal prototype reduces the 8,192-root DagQL prune fixture from 5.122 seconds to 46.06 ms. Full Go listing does not improve (47.47 to 48.66 seconds), with no metadata prune in that cohort. The diagnostic deletion switch remains off; its reverse index is common to both arms. See [the report](../../NATIVE_RESTORED_POSTING_REMOVAL.md). No PR is opened.

The manifest verifies source and archived bytes. Large text captures use gzip. Raw Go source lives under testdata. Executables are omitted with hashes. Build inputs, sources, test logs, complete-command samples and rejected observations are retained. The preceding combined profile supplies the recorder evidence; no after-module recorder capture was run for the workspace-path candidate. No database, snapshot contents or Git metadata are included. The pinned telemetry SDK/module copies are identified by ../otel-evicted-queue/. Drivers contain local paths requiring adaptation.
