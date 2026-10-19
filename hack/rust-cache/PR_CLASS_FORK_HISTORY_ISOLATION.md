# fix(dagql): isolate field override histories across class forks

Class.ForkObjectType copies the field map but retains the backing arrays of its per-name override histories. If a history has spare capacity, the parent and fork can append into the same slot. The later append silently replaces the other branch's definition.

Clip each existing history's capacity before appending in Install and Extend. Both branches retain their previous entries, and the next append receives independent storage.

This was found while investigating schema preparation during Go test collection listing on dagger/dagger. It is a correctness fix; no listing speedup is claimed.

### Regression

Install three versions of a field, fork the class, and install a different fourth version in each branch. On upstream main 18d51f8291, the parent unexpectedly returns the fork's definition. The same regression passes with the fix.

Both Install and Extend are covered, and the race check passes.

### Scope and tradeoffs

Two production lines change. No locks, cache identities or fork APIs change. Appending an override can allocate where it previously reused spare capacity; read-only forks are unaffected.

This is independent of the proposed class copy-on-write optimization and should be reviewed separately.

[Source](https://github.com/grouville/dagger/tree/fix/class-fork-history-isolation). [Reproduction and validation](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/class-fork-history-isolation).
