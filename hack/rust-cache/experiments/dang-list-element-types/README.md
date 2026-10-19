# Dang SDK list element-type regression

[Fix 231995ae7f](https://github.com/grouville/dagger/commit/231995ae7f4b0a2c5edc863addd946bad05ff8b2) is based directly on upstream main `ff0b029a4d270a651b9a8c7286babc79089066e4`. See the [report](../../NATIVE_DANG_LIST_ELEMENT_TYPES.md) and [review description](../../PR_DANG_LIST_ELEMENT_TYPES.md). No PR is open and no latency benefit is claimed.

`fix.patch` contains one production-line change and the four-case regression. `identity.json` identifies the source. `steps.json` records the final baseline failure, candidate success and full SDK package race-suite success.

`evidence.tar.gz` retains exact before/after helper source, the final test, verification script and logs. `initial-assert-format/` contains the earlier equivalent structural assertions and their results; the final test prints concise type signatures instead. The current upstream helper identity was checked independently before implementing the fix.

`manifest.json` records every archive member's size and SHA-256. All members were verified after compression. `archive.json` identifies the archive. Executable binaries are excluded.
