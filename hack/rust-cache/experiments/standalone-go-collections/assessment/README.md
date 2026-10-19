# Contribution assessment

PRs #14732 and #14733 were closed after assessing real-workload value against complexity. Their benchmark improvements remain valid, but do not establish worthwhile current-main collection-listing contributions. Comments explain the supporting older evidence and its limitations.

The unchanged-main engine comparison contains 16 Go modules and real source/test edits, fresh CLIs, ordinary telemetry and cleanup. Each candidate starts from Go module main independently. Both the generation-matching and membership comparisons include every raw sample, including slower candidates. The matching change is promising; native membership is held after regressions. Neither is an opened PR.

The cache census is read-only and runs after all timed commands. It records reported types, not the exact disk-usage eligibility predicate. Its 6,581 results and 147 String results describe this smaller fixture after the cohort, not a complete dagger/dagger listing or the peak at cleanup. The compressed source snapshot stays local; its hash and size are recorded.

Future proposals require a written benefit/complexity/risk decision before opening. A faster microbenchmark alone is not enough. Useful evidence includes a meaningful complete-command improvement, a substantial resource cost established on a real cache, or a genuine correctness regression against current main. Controls must show the cost on paths that cannot benefit. Branches and evidence remain available when proposals are held or closed.
