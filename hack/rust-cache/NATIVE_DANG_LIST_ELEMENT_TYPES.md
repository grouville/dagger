# Correct the runtime type of converted SDK lists

The active Dang v2 SDK converter restores a JSON array with `ElemType: listT`, where `listT` describes the whole list. `ListValue.Type()` wraps its element type in a list, so converting `[String!]!` reports `[[String!]]!`. The serialized value remains a flat array.

The standalone fix uses `listT.Type`, the declared element type. It is one production line, with a regression covering flat strings, empty lists, nullable elements and nested lists. The test checks the reported type and serialized contents. All four cases fail on clean upstream and pass with the fix. The complete SDK package race suite also passes.

The base is current upstream main `ff0b029a4d270a651b9a8c7286babc79089066e4`, fetched during this audit. Upstream's helper blob is `02832f36bbb320ea725c9e2d0b64463f7ac1c366`. This is live code: the allocation profile records `dangConverter.convertList` while real collection getters run. It is not the unused BuildKit path from the earlier cache investigation.

[Fix 231995ae7f](https://github.com/grouville/dagger/commit/231995ae7f4b0a2c5edc863addd946bad05ff8b2) is pushed to `fix/dang-list-element-types` on the fork. The [review description](PR_DANG_LIST_ELEMENT_TYPES.md) is prepared; no PR is open. The fix has not been installed in the benchmark engines and has no measured latency claim.

[Evidence](experiments/dang-list-element-types/) retains the exact source, patch, before/after regression output and complete SDK race result. The initial structurally equivalent assertions produced large type dumps; the final regression uses readable type signatures and was rerun before and after the fix.
