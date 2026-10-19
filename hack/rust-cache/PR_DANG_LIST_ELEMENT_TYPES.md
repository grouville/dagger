# fix(dang): keep the element type when converting a list

While investigating Go test collection listing, I found that the Dagger SDK could turn a list of strings into a value whose reported type was a list of lists.

The converter puts the whole list type in Dang's `ListValue.ElemType`. Dang then wraps that type in another list when reporting the value's type. For example, `[String!]!` is reported as `[[String!]]!`.

Store the element type in `ElemType` instead. This changes one line in Dagger's Dang converter. The contents and serialized output stay the same; the reported type matches the list that was received.

### Reproducing

The regression covers strings, empty lists, nullable elements and nested lists. Each case checks the reported type and JSON contents. All four fail on main `80699ac67a` and pass with this fix:

```sh
go test -race -count=1 ./core/sdk/dang/v2 -run '^TestConvertListPreservesElementType$'
```

To check the rest of the converter and SDK tests:

```sh
go test -race -count=1 ./core/sdk/dang/v2
```

This is a type-correctness fix found during the performance investigation; it does not claim a speedup.
