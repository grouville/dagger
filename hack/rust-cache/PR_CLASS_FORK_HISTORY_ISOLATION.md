# fix(dagql): keep copied schema types independent

Changing a copied schema type can accidentally change the original too. I found this while working on Go test collection listing.

A schema field can have different definitions for different API versions. `Class.ForkObjectType` copies a type so those definitions can be changed independently. But adding a new definition to both the original and the copy can produce this:

| Type | Expected definition | Before this fix |
| --- | --- | --- |
| Original | The original's new definition | The copy's new definition |
| Copy | The copy's new definition | The copy's new definition |

The field map is copied, but the arrays holding its definitions are still shared. If an array has unused space, both types append into the same slot. The second write overwrites the first.

Make appending use a separate array. This changes two lines, in `Install` and `Extend`, and adds no locks. Existing definitions can remain shared.

The cost is an extra allocation when adding a definition that previously fit in unused array space. Installing a field for the first time behaves as before.

The regression creates three definitions, copies the type, then adds a different fourth definition to each. It covers both methods, fails on main `c5456d9cbf`, and passes with the fix:

```sh
go test -race -count=1 ./dagql -run '^TestClassForkHistoryIsolation$'
```
