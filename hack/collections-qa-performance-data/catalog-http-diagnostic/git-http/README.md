This is instrumentation only. It leaves anonymous Git visibility checks, per-session freshness, service-bound exceptions, go-git's shared HTTP transport, credentials, retry/redirect behavior and the returned canonical ref metadata unchanged. It is not a visibility-cache or protocol optimization.

The diagnostic overlay is derived from the retained parent-metadata candidate engine, preserving its frozen experimental SDK/Dang sources and module pins. Current repository HEAD and retained behavior ancestry are recorded separately in builds/recipe.json. Source-context loading still happens before SDK loading; the new nested timer contexts only identify their actual work.

The finite HTTP labels record timestamps and outcomes, never hosts, URLs, headers, credentials, error strings or response bodies. Connect callback keys live only in memory to match concurrent attempts and are not recorded. Existing HTTP trace hooks compose normally. Hooks are installed only when wcprof.Enabled(ctx). The main validation/materialization phase markers are inactive without profiling.

Interpretation:

- getConn includes acquisition plus any DNS, connection or TLS work beneath it. Do not sum those overlapping intervals.
- connectionNew/connectionReused, requestWritten and firstByte are zero-duration count events.
- writeToFirstByte measures an observed successful write callback to the first response byte. This is not server CPU or an RTT measurement.
- A first response byte may precede WroteRequest. That produces firstByteBeforeWrite and disables subsequent write pairing for this advertisement; no duration is fabricated from a later redirect's callbacks. Repeated unresolved writes produce writePairingAmbiguous with the same conservative handling.
- lastFirstByteToParsed includes remaining response headers, body transport, pkt-line decoding, capability filtering and go-git return handling. With redirects it starts at the final first-byte observation. It does not isolate bytes or decoding CPU.
- readAndDecode spans the complete AdvertisedReferencesContext call. validateAllReferences measures its separate compatibility validation; materializeAndSort measures Dagger's canonical conversion.
- Losing connection attempts may finish after the advertisement returns. Completed callback intervals remain observable; incomplete callback pairs emit no completed interval. No open wcprof operations are created by the callbacks.

Prepared validation contains six focused callback test groups (boundaries/privacy, reuse/error, inherited hooks/late connects, concurrent callbacks, redirects/repeated TLS, and first-byte-before-write) plus existing advertisement parity/session semantics and symbolic-HEAD tests. Normal and race results, exact inputs, commands and bounded subprocess setup are recorded in builds. No runtime performance result follows from these tests.

The shared runtime plan uses one diagnostic engine for Docker-exec and direct-Unix connection selectors, then separate fully primed listing profiles. Raw profiles remain private. Only fixed-label aggregate timings and counts may be archived; no remote identifiers or payloads are needed to answer which phase dominates.
