Closing this for now: the isolated benchmark improvement does not yet justify the added filesystem traversal logic.

The largest result, 2.51 ms → 49.87 µs, uses a selected path surrounded by 2,048 unrelated directories. With eight unrelated directories the saving is about 8 µs. The change adds 77 implementation lines and has to preserve ancestor permissions, symlinks, cancellation and callback behavior. The parity tests cover those cases, but a faster artificial walk is not enough to establish the payoff.

An older complete-listing experiment improved 55.81 → 52.03 seconds in two measured pairs. That used the experimental engine/module and additional CLI changes shared by both arms. It is supporting evidence, not a result for this PR alone on current main.

Before proposing this upstream, I want a complete listing comparison on a clean main baseline, with the actual call count and time spent in these imports. The source branch and raw measurements remain available on the fork; this can be reopened if that evidence justifies the complexity.
