# Native string-sort experiment

This branch requires the local experimental Dagger engine that adds Dang's `sortStrings` builtin. It does not work with stock beta.15 despite retaining that module minimum for the baseline comparison. The builtin name and public API are provisional; this branch is for performance and correctness review, not release.

The only production module change replaces three private insertion-sort helper bodies with the typed native string sorter. Go byte ordering, duplicates, collection granularity and source policy remain the same. The shared-library check expands file-policy coverage, including nested modules, Unicode, newlines and similarly named excluded paths.

Full command measurements must use the same engine, CLI and fresh edits for both module variants. Component speedups alone do not establish a complete listing improvement.
