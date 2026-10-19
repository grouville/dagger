# fix: preserve list item types in nested selections

While working on Go test collection listing, I hit a valid Dang program that the compiler rejected. It selects fields from a list inside another list, then collects the text values:

```dang
let selected = pages.{{matches.{{text}}}}
```

The input types say that neither a match nor its text can be null. The collected texts should therefore have type `[String!]!`. But after the nested selection, Dang treats them as `[String]!`. The missing `!` means an item could be null, so combining those texts with a list of required strings fails:

```text
cannot use [String]! as [String!]!
```

The nested-selection code forgets whether list items could be null. Preserve that information when constructing the selected type, as ordinary selections already do.

The regression runs a complete program and checks the returned strings and their order, including an empty nested list. Two other cases check that values whose types really allow null are still rejected where required strings are expected.

The valid program fails on main `bf649b8d` and passes with the fix. The full interpreter suite also passes with the race detector:

```sh
go test -race -count=1 ./pkg/dang
```
