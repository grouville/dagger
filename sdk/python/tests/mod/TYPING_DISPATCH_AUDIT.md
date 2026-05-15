# Typing.py Dispatch Audit

> **Branch context:** this document lives on the
> `python_sdk_typing_conformance_exploration` branch (a personal fork
> branch, not a merge candidate). It captures research outputs that
> informed the main PR but doesn't ship as production code. The
> companion exploration on this branch is the
> `tests/mod/test_external_corpus.py` harness + the vendored corpora
> in `tests/mod/external_corpus/`.

A structural map of `typing.py`'s resolution machinery against the Dagger
AST analyzer. Each row is a dispatch point in CPython's `typing` module
(where typing decides what to do based on the shape of input). For each,
this document records: what typing does, our analyzer's equivalent code
path, and known/predicted bug classes.

The point of this audit: bugs we keep finding (PR #13149 + 5 more found
in the same session) are all "code path X doesn't apply alias expansion
the way code path Y does." Rather than discovering each gap by Hypothesis,
this matrix predicts them by reading typing.

## Stats: external corpora baseline

The harness ran the analyzer (at the state on this branch's parent —
i.e. main with PR #13149 already merged) against three external corpora:

| Corpus | Annotations checked | OK | Out-of-scope | Real divergences |
|---|---|---|---|---|
| **typing/conformance** (community standard) | 517 | 214 | 300 | 3 (naming convention noise) |
| **pyright samples** (curated subset) | 289 | 49 | 239 | 1 (generic substitution, OOS) |
| **jedi pep0484_typing.py** (curated subset) | 21 | 15 | 0 | 6 (harness limitations — see note) |
| **Total** | **827** | **278** | **539** | **0 real bugs in scope** |

**Key finding:** none of the external corpora caught the bug class
PR #13149 fixed, nor any of the 5 bugs found in this session via
Hypothesis grammar extension.

Why not: all three corpora are built for type *checkers* (pyright, mypy,
ty), not type *extractors*. They thoroughly test type vocabulary and
diagnostic behavior but rarely combine alias resolution with the
specific AST positions where Dagger's analyzer has selective dispatch.

The 6 jedi divergences are caused by a known harness limitation
(`test_external_corpus.py` calls `Resolver.resolve()` directly without
going through the parser's alias-collection step); fixing the harness
would require wrapping every fixture as a Dagger-decorated module —
back to the friction the per-annotation harness was designed to avoid.

## Top-level: `typing.get_type_hints(obj)` — `typing.py:2186`

Walks `obj.__annotations__`, evaluates string annotations against the
module's namespace, strips Annotated metadata (unless `include_extras`),
returns dict[name, resolved_type].

| Typing step | Our equivalent | Coverage |
|---|---|---|
| `for base in reversed(obj.__mro__)` — walk MRO for inherited annotations | `parser.py` walks MRO via `_collect_mro_annotations` | ✅ PR #13095 |
| `ann = base.__dict__.get('__annotations__', {})` — get annotations dict | `parser.py` walks ClassDef body for AnnAssign | ✅ |
| `if isinstance(value, str): value = ForwardRef(value, …)` — wrap strings | `resolver._resolve_ast` handles `ast.Constant(value=str)` (line 290) | ✅ partial — see ForwardRef rows below |
| `value = _eval_type(value, base_globals, base_locals)` — resolve recursively | `resolver.resolve` + `_expand_alias` | ⚠️ **gap** — see _eval_type rows below |
| `_strip_annotations(t)` (when not include_extras) | `visitors/annotations.py:unwrap_annotated` | ✅ |

## Core: `_eval_type(t, globalns, localns)` — `typing.py:406`

The recursive dispatcher. Switches on the value's runtime type and
recurses through nested args.

```python
def _eval_type(t, globalns, localns, recursive_guard=frozenset()):
    if isinstance(t, ForwardRef):
        return t._evaluate(globalns, localns, recursive_guard)
    if isinstance(t, (_GenericAlias, GenericAlias, types.UnionType)):
        ev_args = tuple(_eval_type(a, globalns, localns, recursive_guard) for a in t.__args__)
        ...recurse into args, reconstruct...
    return t
```

| Typing dispatch | Our equivalent | Coverage |
|---|---|---|
| `isinstance(t, ForwardRef)` → `_evaluate` | `_resolve_ast` for `ast.Constant(str)` calls `_resolve_name` | ⚠️ **gap**: `_resolve_name` doesn't call `_expand_alias` on the result — **Bug 3** territory (alias inside forward ref under future annotations) |
| `isinstance(t, _GenericAlias)` → recurse `t.__args__` | `_resolve_ast` for `ast.Subscript` recurses into slice via `_resolve_subscript`, then resolves each element | ⚠️ **gap (fixed this session)**: `_expand_alias` didn't recurse into Subscript slice — **Bug 1b** (`Optional[Alias]`) |
| `isinstance(t, types.UnionType)` → recurse `t.__args__` | `_resolve_ast` for `ast.BinOp(BitOr)` recurses via `_resolve_union` | ✅ **fixed by PR #13149** — was Bug 1 |
| `recursive_guard` to prevent cycles | `_expand_alias` has `seen` set | ✅ |
| Reconstruct after recursion (`t.copy_with(ev_args)`) | We build new AST nodes after expansion (BinOp/Subscript) | ⚠️ Bug 1b fix uses this pattern; pattern needs uniform application |

## `ForwardRef._evaluate` — `typing.py:909`

Resolves a string annotation by calling `eval()` in the controlled
namespace, then **recursively calls `_eval_type` on the result**.

```python
type_ = _type_check(eval(self.__forward_code__, globalns, localns), ...)
self.__forward_value__ = _eval_type(type_, globalns, localns, ...)
```

| Typing step | Our equivalent | Coverage |
|---|---|---|
| `eval(code, globalns, localns)` to resolve string | `namespace.eval_annotation` calls `eval(..., ns)` | ✅ |
| **Then recurse `_eval_type` on the result** | We have a parsed AST after eval, but call `_resolve_evaluated` which doesn't re-walk through `_expand_alias` | ⚠️ **gap**: alias inside forward ref → no expansion pass — **Bug 3** mechanism |

## `_GenericAlias.__class_getitem__` — `typing.py:2087`

When you write `List[int]`, Python calls `list.__class_getitem__(int)`,
which constructs a `_GenericAlias` with the args. typing handles this
at *expression-build time* — by the time `get_type_hints` looks at the
annotation, `List[int]` is already a structured object.

| Typing capability | Our equivalent | Coverage |
|---|---|---|
| Construct `_GenericAlias` from `(origin, args)` | We don't construct anything — we walk AST directly | ✅ different model |
| `Annotated[Annotated[T, M1], M2]` flattens to `Annotated[T, M1, M2]` via `_AnnotatedAlias.copy_with` | `visitors/annotations.py:unwrap_annotated` is single-level | ⚠️ **gap**: nested Annotated flattening through alias — **Bug 2** territory |
| `_GenericAlias.copy_with(new_args)` substitutes type variables | We don't implement substitution at all | ❌ Out of scope — Dagger rejects TypeVar/Generic anyway |
| `__class_getitem__` for `Optional[T]` returns `Union[T, None]` | We translate `Optional[T]` → `T | None` in resolver | ✅ |

## `_strip_annotations` — `typing.py` (companion)

Walks the tree, removing `_AnnotatedAlias` wrappers but keeping inner
types. Used when `get_type_hints(include_extras=False)`.

| Step | Our equivalent | Coverage |
|---|---|---|
| Recurse into `__args__`, strip nested Annotated | `unwrap_annotated` strips outer Annotated only | ⚠️ Partial — nested Annotated inside Optional/list isn't always stripped uniformly |

## Predicted bug classes (from this audit)

Based on the gaps above, here are bug classes we should expect — including ones Hypothesis hasn't surfaced yet:

### Confirmed bugs in this session

1. **`Alias | None`** (`ast.BinOp` doesn't recurse to expand sub-aliases) — fixed by PR #13149
2. **`Optional[Alias]`, `list[Alias]`** (`ast.Subscript` doesn't recurse to expand sub-aliases) — fixed in this session
3. **Alias inside nested forward ref under `from __future__`** (`_resolve_name` doesn't run alias expansion on forward-ref string contents) — deferred

### Predicted bug classes not yet surfaced

The pattern is: **any AST node that *contains* a name reference and isn't `BinOp(BitOr)` or `Subscript` is suspect.** Specifically:

- **Alias inside `Annotated[Alias, M1, M2]` slice tuple** — partially exercised in Bug 2, but the metadata-extraction path may also need to be checked
- **Alias inside class-base specification** — `class Foo(Helper)` where `Helper` is an alias of another class. Probably broken because `_expand_alias` isn't called on base specs
- **Alias inside default value type** — `def f(x: int = MAX)` where `MAX` is itself a type-alias rather than a value constant. Edge case
- **Alias in return-type forward ref** — `def f() -> "Alias"` under future annotations. Probably same shape as Bug 3
- **Alias used as a generic parameter to a Dagger type** — e.g. `dagger.Container[Alias]`. Already rejected (generics rejected), but worth confirming rejection message is right
- **Alias chained through PEP 695 `type X = …`** — particularly `type X[T] = ...` (generic PEP 695), already rejected
- **Multiple Annotated nesting through aliases** — `type X = Annotated[T, M1]; type Y = Annotated[X, M2]; def f(x: Y)` — Bug 2 sibling

### Bug classes that are explicitly out of scope

- TypeVar substitution / generic instantiation
- `ParamSpec`, `TypeVarTuple`, `Concatenate`
- `Callable[…]` resolution
- `Literal[…]`, `dict[K, V]` — Dagger explicitly rejects

## What this tells us

**Three observations:**

1. **All confirmed and predicted bugs cluster on one structural issue:** `_expand_alias` is selectively applied per code path. The fix pattern is uniform (recurse through children), but the application points differ.

2. **The grammar caught everything we predicted to find.** Hypothesis is doing the work of the audit empirically. The audit's value is producing a stopping criterion: once the grammar covers all the "container nodes" (BinOp, Subscript, forward-ref-string, Tuple, class base), we should see no new bug classes.

3. **The audit predicts ~5-7 more bug classes the grammar hasn't surfaced.** If we want to find them, the grammar dimensions to add are:
   - Aliases used as class bases (`class Foo(AliasOfHelper):`)
   - Aliases in return-type forward refs
   - Aliases chained through multiple Annotated layers
   - PEP 695 `type X = ...` chains used in unions

## Recommendation

For the current PR:

1. **Don't try to find all bug classes.** The audit shows we'd add 5-7 more grammar dimensions, fix ~5-7 more recursion points in `_expand_alias`. That's a multi-PR effort.

2. **Fix Bug 1b (Subscript) and Bug 3 (forward-ref under future annotations) in this PR.** Both are mechanically similar — one-line additions to `_expand_alias`. The Subscript fix is already done. Forward-ref-under-future-annotations needs the alias expansion in `_resolve_name`.

3. **Document Bug 2 and the predicted bug classes.** File as follow-ups.

4. **The bigger architectural point stays:** every bug found here is in `_expand_alias`'s selective application. Switching to jedi/ty as the resolver makes this whole bug class disappear by construction (their dispatch is uniform). Worth raising as a separate architectural conversation, but out of scope for this PR.
