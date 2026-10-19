# dagql: isolate field override histories across forks

Class.ForkObjectType copies the field map but retains the backing arrays of its per-name override slices. If an override history has spare capacity, the parent and fork can append into the same slot. The later append silently replaces the other branch's field definition.

The regression checks both Install and Extend. It installs three versions, forks the class, then installs a different fourth version in each branch. On main the parent's definition becomes the fork's definition. With the fix each branch retains its own override.

Clip the existing history's capacity before appending in Install and Extend. This forces a new backing array instead of writing into shared storage. The existing entries and order remain the same. No locks or cache identity change.

The regression fails against freshly verified upstream main, 18d51f8291, with expected parent and actual fork. It passes with the two-line fix and the race detector. The tradeoff is an allocation when appending an override that would otherwise reuse spare capacity; read-only forks are unchanged. No listing speedup or production incident is claimed.

[Source and regression evidence](experiments/class-fork-history-isolation/).
