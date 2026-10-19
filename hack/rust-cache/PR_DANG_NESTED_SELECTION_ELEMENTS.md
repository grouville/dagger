# fix(dang): preserve non-null elements in nested list selections

Nested selection changes a list of required objects into a list whose objects appear nullable. Mapping their required string fields then fails with "cannot use [String]! as `[String!]!`". An otherwise valid program cannot compile.

Carry the inferred element's non-null marker into the nested selected list type, as the top-level selection path already does. Runtime values and the outer list retain their existing behavior.

This was found while reducing Go test collection listing overhead on dagger/dagger: a normal nested selection over test-file search results exposed it. It is a correctness fix; no speedup is claimed.

### Regression

A complete nested-selection program fails on pristine Dang da1bed304c and passes with the six-line inference change. The test verifies values and order, including an empty nested list, and keeps nullable elements and nullable fields rejected.

The full pristine upstream interpreter, development interpreter and Dagger SDK race suites pass. Seven focused real-module checks pass after rebuilding the experimental engine, including the previously rejected selection, Unicode ordering, source overrides, test execution, binaries and generation.

### Scope

The standalone patch changes type inference and its regression only. It adds no cache, lock, scheduling change or engine API.

[Standalone patch](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/experiments/dang-nested-selection-elements/standalone.patch). [Reproduction and validation](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_DANG_NESTED_SELECTION_ELEMENTS.md).
