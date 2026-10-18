Review draft for a standalone patch against upstream Dang `da1bed304cb80f8a2f0714f1747e7f64e03297a3`. No PR is open.

Title: **Preserve non-null list elements in nested selections**

Nested selection currently turns a list of required objects into a list whose objects appear nullable. Mapping their required string fields then fails with `cannot use [String]! as [String!]!`. This prevents an ordinary list selection over Go test-file search results from compiling.

Carry the already inferred element's `!` into the selected list type, as the top-level selection path does. The change only adjusts type inference; runtime values and outer-list behavior are unchanged.

The regression runs a complete nested-selection program, verifies its values and order, and keeps nullable elements and fields rejected. Its valid case fails without the patch and passes with it. The full pristine upstream interpreter race suite, development interpreter race suite and Dagger SDK race suite pass. The real module program compiles afterward and its seven focused checks pass.

This fixes a rejected valid program. No performance gain is claimed.
