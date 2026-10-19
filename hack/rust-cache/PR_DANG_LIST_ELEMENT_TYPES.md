# fix(dang): preserve element types when restoring lists

The Dang SDK converter puts the incoming list type into `ListValue.ElemType`. `ListValue.Type()` then adds another list wrapper: restoring a `[String!]!` value reports `[[String!]]!`.

Use the declared element type instead. This corrects runtime type metadata while preserving the array contents and their JSON representation.

The regression covers flat strings, empty lists, nullable elements and nested lists. All four cases fail on current main and pass with the one-line fix. The full `core/sdk/dang/v2` race suite passes.

This is a correctness fix; no performance gain is claimed. [Source and evidence](NATIVE_DANG_LIST_ELEMENT_TYPES.md).
