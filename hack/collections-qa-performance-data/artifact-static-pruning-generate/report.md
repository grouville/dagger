# Selected generator and actual generation follow-up

All four correctness commands passed using the same matched full-pruning engines and d685 CLI as the 38-command trial. No Cloud or profiling occurred.

For each engine, `generate -l dagger-go-sdk/generate` produced exactly the one expected SDK generator row, including its description. Then `-y generate render` consumed a distinct first-seen native input and wrote exactly those bytes to the generated file. This proves a real generation consumer, but native generation is not SDK code generation.

Observed baseline/candidate native command times were 422.0/447.4 ms, with correct output visible at 397.3/425.3 ms. The selected listings took 1933.2/1727.2 ms after engine restart. These are one correctness/setup observation per arm, not a latency comparison.

All fixture bytes were restored; original engine and heavy init remained untouched and stopped; retained volume was preserved; temporary engine removed. No further commands ran. These results belong to the complete tested pruning prototype, not a hypothetical narrower variant.
