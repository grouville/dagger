# Preserve non-null elements in nested selections

A normal nested list selection rejects valid code because it drops the element's existing `!` type marker. Selecting a required field from `[Row!]!` then appears to produce nullable values. The Go test-file parallel-read experiment exposes this as `cannot use [String]! as [String!]!` before any benchmark can run.

The standalone regression reproduces on pristine upstream Dang commit `da1bed304cb80f8a2f0714f1747e7f64e03297a3`. A six-line change in `ObjectSelection.inferFieldType` preserves `ElementIsNonNull` when constructing the nested list type, matching the existing top-level selection path. It does not alter outer-container behavior, runtime evaluation, cache identity, locks or scheduling.

The regression runs a complete program that selects nested records, maps required string fields, and concatenates results across a populated and an empty list. It checks output order. Two negative cases keep nullable elements and nullable fields rejected. Without the patch the valid case fails; with it all three pass.

The full pristine upstream interpreter race suite passes, as do the development interpreter and Dagger SDK race suites. After rebuilding the isolated Go engine, seven focused module commands pass, including the previously rejected nested-selection program, ordering across ASCII/Unicode filenames, empty files, source overrides, additions/removals, collection execution, binaries and generation.

This is a correctness fix, with no performance benefit claimed. Both versions of the subsequent parallel-file experiment use it; that experiment regresses test-edited listing and stays unselected. The fix does not imply that parallel reads should be adopted.

Engine `053e9d5db9959b04259d48b8fc635721cfc7375652b43953010f767f7bf16118` runs in the same isolated Go container and cache volume. Prior overlay entries, including native telemetry storage and its readers, are retained. The original Rust engine remains `1a514c536c6bf10d2463faab2d4e4329f187dd4c0af5f46aba1cbe91460e2fb7`.

[Minimal patch and test](experiments/dang-nested-selection-elements/standalone.patch), [evidence](experiments/go-discovery-setup-screens/), [review description](PR_DANG_NESTED_SELECTION_ELEMENTS.md). No PR is opened.
