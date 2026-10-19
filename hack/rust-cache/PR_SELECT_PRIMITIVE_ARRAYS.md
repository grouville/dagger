# dagql: copy primitive lists into matching value slices

`Server.Select` creates a cache result for every list element, even when its destination only holds plain values. Native workspace globs pay this cost for every filename, including a copy of the list's call frame.

Append a copy of built-in string, integer, float and boolean arrays into matching value slices. Field evaluation, dynamic inputs and operation leases still run. Identity-bearing destinations, explicit Nth selections, object/custom/nullable lists and scalar conversions keep their existing path. This adds ten lines, with no new API, cache or lock.

Four alternating component pairs on Go 1.26.6, selecting a cached list:

| Strings | Before | After | Allocation before → after |
| --- | ---: | ---: | ---: |
| 8 | 34.60 µs | 3.80 µs | 22.15 → 1.84 kB |
| 1,024 | 3.786 ms | 9.128 µs | 2.65 MB → 20.17 kB |

All pairs improve. On the native-directory Go prototype, complete dagger/dagger listing improves **5.43 → 4.86 s** after source edits and **8.29 → 7.86 s** after test edits, faster in all eight pairs, with **606–613 MB** less allocation. Fresh CLI processes, telemetry and cleanup are included on a warm experimental engine.

The selected Go module remains essentially flat at **3.95 → 3.91 s** and **6.86 → 6.85 s** (2/4 faster each). The broader native-directory module remains slower and unselected. No cold-start gain is claimed.

The regression fails on main on unnecessary element cache entries. Tests cover copied storage, values/order/duplicates/append behavior, loadable identities, Nth selection, conversions, per-call evaluation, authored errors and released sessions. Both main-based and development DagQL race suites pass, along with 32 Go checks, 28 Rust/native-cache cases and 48 timed listings. Profiles retain all 800 authored getters and 799 unchanged test-discovery hits after a test edit.

[Source, complete attempts and measurements](NATIVE_SELECT_PRIMITIVE_ARRAYS.md).
