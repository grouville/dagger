# fix(dang): keep the element type when converting a list

Dagger can pass the right list values to Dang but attach the wrong type to them. I found this while working on Go test collection listing.

For example:

| Value | Expected type | Type before this fix |
| --- | --- | --- |
| `["first", "second"]` | `[String!]!` | `[[String!]]!` |

The extra pair of brackets says each item is another list, even though the items are strings.

A Dang list stores the type of **one item** in `ElemType`. The SDK currently fills that field with the type of **the whole list**. Dang then adds another list wrapper when reporting the value's type.

Change that one line to store the item type instead. The values, their order and their JSON output stay the same.

The regression checks ordinary lists, empty lists, nullable items and nested lists. Each case checks the type and JSON output. All four fail on main `c5456d9cbf` and pass with the fix:

```sh
go test -race -count=1 ./core/sdk/dang/v2 -run '^TestConvertListPreservesElementType$'
```
