This is a source-only prototype against current production helpers at f743dba65758b678ed9d7261ec3515341cdc3eaf and the checkout's Dang v2.1.4. No tests, compilation, engine calls or timings have been run for it. The historical38711 experimental engine already omits the object-directive pass; it cannot serve as the baseline for this change.

The current registration path parses the module once for self-type placeholders, invokes Dang's independent declaration/evaluation parser, then parses the source again to attach object directives. The prototype combines only the first and third metadata reads. It does not reuse the evaluator's AST, inferred environment, schema, runtime results or authority. Metadata lives inside one mounted immutable module Directory callback.

Each file retains its own parse error in sorted file order. Names skip failed files and retain the main-type fallback. After the unchanged runner succeeds, directive processing walks the same ordered file records: an earlier constructor lookup error still precedes a later file's parse error. If the runner fails, its existing source rendering/short-error behavior wins and no directives are applied. Public-name filtering and all-object directive retention remain distinct. Raw directive arguments are neither inferred nor evaluated during collection.

`runDangSourceWithRegistration` extracts the prior callback body to make the runtime-skip and actual diagnostic-priority boundary directly testable. It keeps the same wcprof phase labels; `dang.selfTypes` now includes gathering the raw directive pointers, and `dang.objectDirectives` only attaches them. Phase timing must account for that redistribution.

Prepared six focused test groups:

- TestDangRegistrationMetadataParsesOnceForBothConsumers
- TestDangRegistrationMetadataNamesAndPrivateDirectives
- TestDangRegistrationMetadataDeferredErrorOrder
- TestDangRegistrationMetadataRunnerErrorAndRuntimeSkip
- TestDangRegistrationMetadataOwnedSnapshotsAndDirectiveScope
- TestDangRegistrationMetadataRealDeclaration

The parser-count test processes two real parsed files through both metadata consumers and requires one parse per file, excluding the unchanged independent runner. Tests also cover existing schema entries, aliases, private directives, missing directories, sequential error precedence, exact rendered source errors, a runtime call on an absent metadata directory, lexical directive argument lookup, separate mutable ownership, concurrent registrations and a fresh source snapshot.

A later approved gate should use the current ordinary checkout dependencies, `test-overlay.json`, these five groups plus existing TestReportDangSourceError/TestDangSourceErrorKeepsGraphQLExtraction/TestDangSourceMessage groups, then repeat with race. Do not substitute the frozen experimental engine.mod: that would erase the production-only comparison. A meaningful negative count witness can restore a second metadata read at the caller (using the same injected parser), and should fail the once-per-file assertion. Real engine parity should subsequently include collection annotations, malformed sources and both legacy registration and ordinary runtime paths before adoption.

The mounted Directory's immutability is the consistency boundary. This is not a filename, session or global AST cache. Inputs created in another invocation are parsed again, even at the same path. Complexity removes one O(source bytes) metadata parse and a directory read per registration; inference complexity is unchanged, and temporary directive AST ownership lasts until registration finishes.

The real declaration witness resolves Dagger.Main through imported schema placeholders, creates actual Dang constructors, infers @collection through DeclareDir, and verifies the separate raw directive AST remains uninferred before and after retention. Raw directive nodes now survive across runSource; total parsing work falls but no peak-memory saving is claimed.
