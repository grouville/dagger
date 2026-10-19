# fix(dang): preserve element types when restoring lists

The Dagger SDK's Dang converter stores an incoming list's whole type in ListValue.ElemType. `ListValue.Type` then adds another list wrapper: restoring `[String!]!` reports [[String!]]!.

Store the declared element type instead. Runtime contents and their JSON representation remain unchanged.

This was found while profiling Go test collection listing on dagger/dagger, where list conversion runs during collection getters. It is a correctness fix; no speedup is claimed.

### Regression

A table checks flat strings, empty lists, nullable elements and nested lists. All four cases fail on upstream main ff0b029a4d and pass with the one-line fix. Each case checks both the reported type and serialized contents.

The full `core/sdk/dang/v2` race suite passes.

### Scope

The change belongs to Dagger's SDK converter, rather than the standalone Dang interpreter. It changes one production line and adds no cache, lock or runtime representation. It has not been installed in the benchmark engines, so no performance conclusion is attached to it.

[Source](https://github.com/grouville/dagger/commit/231995ae7f4b0a2c5edc863addd946bad05ff8b2). [Regression and validation](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_DANG_LIST_ELEMENT_TYPES.md).
