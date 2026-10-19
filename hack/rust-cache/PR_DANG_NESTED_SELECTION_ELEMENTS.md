# fix: preserve required elements in nested list selections

A nested selection can make Dang reject a valid program. We hit this while working on Go test collection listing, when selecting fields from lists of test-file search results.

For a list declared to contain required objects, selecting their fields should preserve that requirement. The nested-selection code drops it, so accessing a required string field later produces `[String]!` instead of `[String!]!`. Combining that result with a list of required strings then fails with `cannot use [String]! as [String!]!`.

Preserve the element's non-null marker when building the nested selected type, as the top-level selection already does. Nullable elements and nullable fields must still be rejected where required strings are expected.

### Reproducing

The regression runs a complete program that selects `pages.{{matches.{{text}}}}`, combines the nested lists, and checks the values and their order. It includes an empty nested list, plus cases where the elements or fields really are nullable.

The valid case fails on main `da1bed304c` and passes with this fix; the nullable cases stay rejected:

```sh
go test -race -count=1 ./pkg/dang -run '^TestNestedSelectionPreservesElementNullability$'
```

To check the rest of the interpreter:

```sh
go test -race -count=1 ./pkg/dang
```

This changes type inference, with no claimed speedup or change to runtime values.
