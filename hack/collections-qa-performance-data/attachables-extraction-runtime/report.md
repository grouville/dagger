# Extracted attachables helper: real SDK correctness

**All 10 local checks passed:** Go module source read, TypeScript runtime build/read, Python constructor/default-factory read, a selected Go check with a unique test-body edit, and an ordinary container exec, once per helper binary.

Both arms used the same ordinary ec6 engine and original d685 CLI. Only the heavy init binary changed; no light PID1 or separate helper mount was used. The container exec verified the mounted `/.init` hash for its arm and absence of `/.dagger-session`. Go, TypeScript and Python fixture configurations explicitly disable default function caching; selected Go test bodies and ordinary exec arguments were unique. No profiler or process-count measurement was used.

The driver validated exact source/file contents and the selected check's successful result, then verified complete restoration: original engine/init unchanged and stopped, all fixtures restored, temporary container removed, retained volume preserved. It made zero Cloud calls and deleted zero volumes. Engine writes bracketing the ten commands totaled 1,273,856 bytes.

These are correctness/setup calls, including SDK preparation and fresh Go compilation. Their raw durations are retained in summary.json, but are not a performance comparison. The independent warm-host helper startup measurement remains 9.114→6.357 ms median over twelve alternating pairs; it does not establish a whole-CLI improvement.

Validation covers Linux/amd64. Moved production bodies keep existing platform behavior; the new Unix socket test needs a platform constraint for a portable upstream suite. Exported aliases preserve ordinary source API use, while reflected defining package paths change. No production source was edited by this driver.
