# Static Go SDK integration: preserved failed proofs

These are correctness gates, not performance comparisons. Both used the same frozen ordinary ec6 engine and d685 CLI, the original init helper, task-owned temporary containers, and fresh copies of the public greetings fixture. Cloud was disabled.

Each trial stopped after its third attempted CLI command. In both, the original SDK generated the backend successfully and actual JSON dispatch passed, including a core Directory receiver, strings, Unicode/list/null arguments and an integer above2^53.

- Trial1 rejected an absolute local SDK source reference before SDK code generation. This was a harness setup error.
- Trial2 used the exact validated PR36 SDK staged inside the candidate workspace and a relative reference. It reached current workspace SDK validation, which rejected the missing `findClientRoot` hook. Source audit also found the required `generateScope` hook absent. No candidate generation or application result is claimed.

Across both trials:6 attempts,4 validated control calls,0 Cloud calls. Both temporary containers were removed; the original engine and init were verified unchanged/stopped, the retained volume preserved, and the original fixture untouched. Trial2 removed the temporary SDK source before cleanup. Complete planned16-call proofs did not finish, so there is no API freshness or performance comparison for the candidate.

The next work is an explicit compatibility bridge for the current workspace SDK protocol, with focused contract validation before any new engine attempt. Metadata generation will continue to use PR36's real generator and live dependency schema.
