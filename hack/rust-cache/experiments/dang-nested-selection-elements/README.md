# Nested-selection element types

[Minimal patch and regression](standalone.patch), [scope and validation](../../NATIVE_DANG_NESTED_SELECTION_ELEMENTS.md), [review description](../../PR_DANG_NESTED_SELECTION_ELEMENTS.md).

The patch applies independently to pristine upstream Dang commit `da1bed304cb80f8a2f0714f1747e7f64e03297a3`. The valid nested-selection program fails without it; the patched program and negative nullable cases pass, along with the full interpreter race suite. No performance gain is claimed.

Full sources, logs, overlays, engine build and activation evidence are in the [combined archive](../go-discovery-setup-screens/). No PR is open.
