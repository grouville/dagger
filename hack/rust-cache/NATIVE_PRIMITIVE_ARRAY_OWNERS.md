# Avoid quadratic ownership walks for primitive arrays

A grouped Rust source-hash query exposed a cache publication cost on the active engine path. Computing 1,026 directory hashes took 52 ms; publishing their string array took another 409 ms. The ownership collectors inspected every string, constructing item call frames that deep-copy the producer's arguments. With N input paths and N output strings, these copies take quadratic work even though the strings own no snapshots or lifecycle state.

The [standalone fix](https://github.com/grouville/dagger/commit/d87815ce1) is based on upstream main `5d313bf2e`. It skips ownership traversal for the concrete built-in string, integer, float and boolean arrays, after validating the authoritative list declaration. Object arrays and custom scalar values retain their existing traversal. The private helper is renamed to describe its ownership purpose. Call identities, hash formats, locks and persistence policy are unchanged.

## Reproduce the cost on main

The benchmark gives an array-producing call as many input paths as output strings, matching the grouped compiler-hash request. Filesystem and compiler work are absent. Three runs use `-benchtime=3x -count=3 -benchmem`; the table gives medians for 1,024 inputs and outputs.

| Ownership phase | Main time | Fixed time | Main allocation | Fixed allocation |
| --- | ---: | ---: | ---: | ---: |
| Collect snapshot links | 193.35 ms | 75.8 µs | 424.6 MB | 207.4 kB |
| Bind inline part hosts | 192.59 ms | 1.08 µs | 424.5 MB | 32 B |

Doubling the input and output count from 512 to 1,024 increases the old snapshot collector's time by 4.34 times and allocation by 3.97 times. The fixed collector retains one linear copy of the producer frame; the part-host walk skips these arrays. These are component measurements, not Rust command speedups.

## Preserve ownership semantics

The adversarial test uses a custom Go value whose schema type is `String`, but which owns a snapshot, binds a part host and has a release hook. Its snapshot path, owning row, binding and single release must survive. This prevents an unsafe shortcut based only on schema names. Another test preserves errors for missing or invalid list declarations.

Both functional checks pass before and after the performance change. Focused inline, snapshot-owner, list-element lineage, part-host lifetime and persisted-list tests pass with race detection on main plus the fix. A real engine's directory-hash integration also passes, covering imported sources, modes, symlinks, ordering, duplicates, empty input and errors.

The experimental engine receives the same small delta through an overlay; it also contains other selected performance experiments. Its grouped-result publication falls from 408.79 ms to 0.63 ms in wcprof. Both captures have no dropped events or open operations. The full grouped-hash request falls from 606.73 ms to 209.50 ms, while an unrelated source-filter request grows and makes that candidate capture slower overall. The local reduction must not be reported as a complete-command gain.

The [grouped package-hash comparison](NATIVE_BULK_PACKAGE_DIGESTS.md) measures complete edited commands with this fix enabled on both module variants. It does not isolate the engine fix's command benefit by itself. A clean restart retains 1,026/1,026 native compilation results; both hashing implementations recover them. The fork branch is pushed and no PR is open.

The [data and raw benchmark samples](experiments/primitive-array-owners/measurements.json) preserve the main baseline, candidate and correctness outcomes. The companion experiment archives the patch applied to the selected engine stack.
