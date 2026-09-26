# Constructor input correctness fixtures — prepared, not run

These three small modules perform the same source operation independently of
greetings-api. Constructors only store the explicit Directory argument; no
constructor reads workspace state or runtime state internally. `read` returns
marker.txt and `verify` fails unless its exact contents are `pass`.

Use the normal Go/TypeScript SDK scaffold and generation workflow to wrap the
provided source in isolated modules named ctor-marker, engineVersion
v1.0.0-0, with ordinary default function caching enabled. The Go module path
must be ctor-marker. Dang consumes main.dang directly. The snippets have not
yet been generated, compiled, or loaded; do not mark them passed from source
inspection. SDK setup may compile runtime tools, but the fixture functions
themselves do not resolve images, start services or invoke compilers.

For each SDK, use a fresh directory and then a second directory/client with
identical module code and layout but different marker content. Run each CLI
call in a new session on the same engine:

1. Write `A` in workspace one and `B` in workspace two. Read A, then B, then A
   again after the first client has closed. Cross-client results must not bleed.
2. Change workspace one's marker to C and read C. Change ignored.txt and read C
   again. The ignored file must be absent from the returned Source directory.
3. Write `pass`, execute the real verify check, write `fail-marker`, require a
   failure containing fail-marker, restore `pass`, and require success.
4. Supply an explicit Source directory whose marker is `explicit`, despite the
   workspace marker being pass. Read must return explicit. This distinguishes
   an explicit immutable argument from a defaultPath provider.
5. Repeat from a nested workspace cwd. The absolute defaultPath remains the
   workspace root. Repeat using a workspace overlay that changes marker.txt.
6. Reuse one SDK client/session and issue two fresh queries across a host edit,
   as TestDefaultPathNoCache does. This catches retaining a contextual host
   provider behind a cached module object inside an interactive session.

Assertions concern content/error propagation, not timing thresholds. Separate
wcprof captures can demonstrate constructor cache hits on unchanged content;
correct output alone cannot prove that any constructor call was avoided.

The main greetings candidate additionally retains PER_SESSION on all five
existing body methods and verifies regenerated metadata. A separate diagnostic
method returning a session token may test that policy across SDKs, but should
not introduce randomness into the constructor under test.
