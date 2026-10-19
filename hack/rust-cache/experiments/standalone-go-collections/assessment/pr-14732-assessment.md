Rechecking whether this change is worth proposing, rather than relying on the stress benchmark alone.

The 200,000-scalar fixture is an existing stress benchmark. It is not a verified count of scalars from one Go test listing. Its result is 998.88 → 459.68 ms and about 68 MB less allocation per cleanup preparation; the smaller provider rows are cost controls.

There is also real-workload evidence: an earlier retained cache had 854,567 mixed results. Switching only this sampler reduced cleanup preparation from 5.12 → 3.22 seconds in all four matched pairs, while preserving the result count and measured usage. The complete Go test listing improved 49.10 → 45.40 seconds in four pairs on that experimental stack. These are not current-main command timings and should not be presented as such. [Recorded measurements and method](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_CACHE_USAGE_PROVIDER_SAMPLING.md).

That makes this a stronger candidate than the filesystem shortcut: it adds 19 implementation lines, uses the existing locks and pruning decisions, and has regressions for values gaining or losing disk usage. I am keeping it draft while checking the representative cache population and complete-command effect on current main. The benchmark alone does not justify claiming that users save half a second.
