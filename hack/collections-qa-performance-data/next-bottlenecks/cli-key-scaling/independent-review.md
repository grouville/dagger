# Independent read-only review

Reviewed current `vertical.py`, `ux.py`, fixture source, and the tracked CLI
formatter change. No builds or runtime calls were made for this review.

## Changes needed before the vertical benchmark

1. **Module-relative default paths do not match the written input.** The fixture
   is under `workspace/module` but reads `@defaultPath("input.txt")` and a source
   directory `@defaultPath(".")`, while the driver writes and expects files at
   the workspace root. `core/modulesource.go:1608` and `:1844` explicitly resolve
   relative paths from the module root. The native workspace entry is not a
   legacy default-path entry. Prefer a `Workspace!` argument and
   `workspace.file("input.txt")` / `workspace.directory(".")`: direct CLI calls
   and artifact groups inject their ambient/bound workspace through
   `core/modfunc.go:1249`. Calibrate both artifact and explicit `-m` paths before
   timing; an absolute annotation needs a verified context root as well.

2. **Intentional up cancellation need not exit zero.** `runServices` returns nil
   on cancellation, but the root CLI explicitly maps a returned context
   cancellation/interruption to status 2 (`internal/cmd/dagger/main.go:1143`).
   Calibrate the exact frontend path; allow only its documented intentional
   interruption result after verified HTTP readiness, and require the tunnel
   to be gone. Do not accept arbitrary nonzero statuses or assume shell 130.

3. **A warm run should not rewrite an identical input.** Currently every command
   writes the marker to `input.txt` again, changing mtime and potentially causing
   filesync/hash work. Compare bytes and write only when they differ. The export
   destination deletion is different: retain it to prove an actual write.

## Boundaries and interpretation

- The tiny core export correctly deletes its destination and verifies exact new
  bytes before reporting success. Its edited content comes from `--contents`,
  however, so it measures a changed export payload rather than input-file
  invalidation. Use `host file(input.txt)` followed by export if that latter
  behavior is intended.
- The file observer measures when the expected bytes become readable, not
  durable fsync completion. Its nominal 5 ms polling interval adds observation
  delay and can miss intermediate states. Full CLI exit remains separately
  measured. An already-current generator is correctly marked as a no-op for
  visibility rather than assigning it a fabricated write time.
- An HTTP readiness sample includes request latency and the polling interval.
  The 100 ms request timeout can widen failed-poll gaps. Keep HTTP readiness and
  cancellation-to-exit separate from total lifetime, which includes deliberate
  shutdown of a long-lived service.
- The free-port reservation is released before launch. A calibrated start should
  confirm the port is still unused; each successful previous run already checks
  its tunnel closes. This is a harness race to detect, not a product failure.
- String API responses use raw text under captured stdout, so comparing exactly
  to the newline-containing marker is appropriate.
- Unique per-variant edit markers avoid accidentally reusing the other CLI's
  cache entry. The shared engine and alternating order are stated; startup and
  image preparation are excluded warm-ups, not cold-volume claims.

## Greetings UX harness

The listed commands exercise normal navigation, artifact listing, generators,
services, file listing, and a real selected check. Exact canonical output and
explicit known key/count assertions supplement each other. Comment/rename/add/
restore probes are correctly labeled correctness checks rather than paired edit
latency claims: the first command can warm the second. The final source restore
checks the independent source fixture too. Profiled calls are excluded from the
warm medians. The CHECKS heading and passed tally share a rendered line, so the
current same-line regex follows the renderer. A first calibration is still
needed for version-specific command names and formatting.

## Formatter source

No correctness issue found. `hasListedArtifactKeys` is exactly equivalent to
asking whether the old unique union is nonempty, including empty keys. The
ordered membership index keeps the first occurrence, compares the complete
`dagaddress.Pair` (dimension, key, HasKey), and allocates only on the ninth unique
pair. Repeated input with at most eight distinct pairs stays bounded by eight
comparisons and avoids a map allocation. Output order and input ownership remain
unchanged. The tests exercise duplicates across the transition, distinct
namespaces, empty keys, and nonmutation. The end-to-end formatter benchmark
includes decode/grouping/rendering; its large-collection result should not be
claimed for the small greetings fixture.
