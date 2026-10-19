# dagql: reuse immutable core field definitions across client forks

Collection expansion creates private clients repeatedly. Each client rebuilds the installed core API's field definitions even though those definitions have not changed.

Prepare immutable field metadata after installing a private core view, then let its class forks reuse it. Keep client/root state private, invalidate a branch on field changes, and use ordinary construction for other views and custom providers. Copy changed nodes during directive filtering so one client's view cannot alter another's definitions. This is stacked on the class copy-on-write and history-isolation changes.

On the experimental full Go listing pipeline, after a test edit:

- Complete command: **6.32 → 6.19 s**, faster in all four alternating pairs.
- Engine CPU: **26.54 → 24.26 CPU-s**, lower in all four pairs.
- Allocation: **5.862 → 5.335 GB**, about **524 MB saved per pair**.

Ordinary-source edits are essentially flat. These are warm development-engine results, including telemetry and successful cleanup, not cold-start or released-engine claims. Both modes execute all 800 authored getters and retain 799 discovery hits. There is no new collection API or stored-result shortcut.

Both full DagQL race suites pass, along with 27 Go checks, 28 Rust/native-cache cases and all 24 timing commands. Regressions cover concurrent first use, branch/view isolation, public metadata mutation and custom definition providers; two negative controls fail without their guards.

The explicit immutable-provider contract adds complexity for a modest elapsed gain. Keep this as an experimental review candidate until that ownership boundary is accepted. [Measurements, limitations and evidence](NATIVE_FROZEN_CORE_FIELDS.md).
