# Navigation and command-completion evidence

See [the report](../../collections-navigation-performance.md) for interpretation.
The archive covers 55 validated commands: 46 ordinary-production-Cloud calls and
nine local setup/correctness calls. Instrumented calls are kept separate from
ordinary latency medians. Native generation is not SDK code generation.

Only explicitly selected numeric reports, source/fixture hashes, driver code and
diagnostic source are included. Raw stdout/stderr, engine logs, wcprof files,
credentials and private API code are excluded. Source paths describe the original
benchmark machine; use the recorded pins/hashes to reconstruct the experiment.

The metric fix is independently validated by real SDK reader and lifecycle tests.
These command timings use the preceding engine binaries and do not establish a
latency improvement from that fix. Cold means a new Dagger volume with an already
available image, and excludes engine provisioning/readiness. The target remains
500 ms for complete commands.
