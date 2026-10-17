# Direct built-in receivers and configuration host reads

See the [receiver results](../../NATIVE_DANG_BUILTIN_RECEIVERS.md) and [configuration analysis](../../NATIVE_CONFIG_LOOKUP_COSTS.md).

- [Final standalone patch](evidence/testdata/final-candidate.patch): interpreter changes, three compatibility guards and the expression benchmark. No diagnostic controls.
- [Measured patch](evidence/testdata/candidate.patch) and [measured sources](evidence/testdata/source-as-measured/): precede the JSON error-wording correction and fixed benchmark expectations.
- [Full-command results](evidence/testdata/full-command-paired/summary.json), [paired differences](evidence/testdata/full-command-paired/paired-differences.json), and every raw command output.
- [Host-read probe](evidence/testdata/toml-host-read-probe/result.json): filtered syscall counts and unchanged configuration hashes. The compressed trace is beside it.
- [Final validation](evidence/testdata/final-validation.json) and [selected engine](evidence/testdata/selected-state.json): include the correction, same-volume restart and native Rust cache checks.

`archive-manifest.json` verifies captured files and their uncompressed SHA-256 identities. `inherited-source-manifest.json` references unchanged sources in the previous sibling archive; every referenced file is verified too. Five executables are omitted, with identities and build commands retained. The implementation targets the measured Dang sources and still needs an upstream rebase. No PR is open.
