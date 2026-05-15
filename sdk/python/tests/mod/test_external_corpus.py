"""Differential test of the AST analyzer against the python/typing conformance suite.

For each vendored Python file in ``external_corpus/typing_conformance/tests/``,
walk every top-level callable and class. For each annotation, resolve it via
the analyzer (``TypeResolver.resolve``) and via ``typing.get_type_hints`` on
the imported module. Assert per-annotation equivalence.

A divergence is a real bug class — the analyzer is failing to mimic
``typing``'s resolution for a pattern the typing community considers in
scope. See ``external_corpus/typing_conformance/README.md`` for context.

Patterns Dagger explicitly rejects (``Literal``, ``dict``, ``TypeVar``,
``ParamSpec``, multi-type unions, etc.) raise ``TypeResolutionError`` from
the analyzer; we record those as ``REJECTED`` and skip the annotation
without failing — they're tested as rejections elsewhere
(``test_ast_analyzer.py``).

Patterns where ``typing.get_type_hints`` itself fails (``"int" | None``
unresolved string-form unions, undefined references, deliberate runtime
errors in test files marked ``# E:``) are recorded as ``ORACLE_ERROR`` and
skipped — our analyzer can't be expected to reach a result the runtime
oracle doesn't.
"""

from __future__ import annotations

import ast
import collections.abc
import contextlib
import dataclasses
import importlib.util
import io
import sys
import types
import typing
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest

from dagger.mod._analyzer.errors import TypeResolutionError
from dagger.mod._analyzer.metadata import ResolvedType
from dagger.mod._analyzer.namespace import build_namespace_from_ast
from dagger.mod._analyzer.resolver import TypeResolver

_CORPUS_ROOT = Path(__file__).parent / "external_corpus"

# Each entry: (label, directory of .py files). Add new vendored corpora
# here — the harness will run the same per-annotation differential against
# each. Labels appear in baseline output and divergence reports.
CORPORA: list[tuple[str, Path]] = [
    ("typing_conformance", _CORPUS_ROOT / "typing_conformance" / "tests"),
    ("pyright_samples", _CORPUS_ROOT / "pyright_samples"),
    # Jedi's full pep0484_typing.py uses incomplete-syntax markers
    # (``y.`` standalone, ``x.setd`` partial-attribute) for their
    # custom completion-test runner that aren't standalone-importable
    # Python. We vendor a curated subset of the standalone-importable
    # sections — see ``jedi_tests/pep0484_typing.py``.
    ("jedi_tests", _CORPUS_ROOT / "jedi_tests"),
]


def _corpus_files() -> list[tuple[str, Path]]:
    """Return ``(corpus_label, file_path)`` for every vendored .py file, sorted."""
    out: list[tuple[str, Path]] = []
    for label, root in CORPORA:
        for path in sorted(root.glob("*.py")):
            out.append((label, path))
    return out


def _import_from_path(path: Path) -> types.ModuleType:
    """Import a Python file as a fresh module without polluting sys.modules permanently."""
    mod_name = f"_corpus_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        msg = f"could not load spec for {path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        # Conformance files often have top-level demo prints. Swallow stdout
        # so the harness output stays scannable.
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(mod_name, None)
        raise
    return module


def _build_resolver_for(tree: ast.Module) -> TypeResolver:
    """Build an analyzer TypeResolver wired to a per-file namespace."""
    namespace = build_namespace_from_ast(tree)
    declared_objects = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    return TypeResolver(namespace=namespace, declared_objects=declared_objects)


def _iter_top_level_callables(tree: ast.Module) -> Iterator[ast.FunctionDef]:
    """Yield top-level function definitions worth comparing.

    Excludes:
    - functions named ``invalid_*`` or ``bad_*`` — conformance convention for
      "this should produce a checker error"; our analyzer correctly refuses
      to eval such expressions while runtime ``get_type_hints`` happily does
    - functions decorated with ``@overload`` — overload signatures aren't
      observable via runtime ``get_type_hints`` (they get erased to the
      implementation)
    """
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith(("invalid_", "bad_")):
            continue
        if any(_decorator_name(d) == "overload" for d in node.decorator_list):
            continue
        yield node


def _decorator_name(d: ast.expr) -> str | None:
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute):
        return d.attr
    if isinstance(d, ast.Call):
        return _decorator_name(d.func)
    return None


def _normalize_runtime(t: Any) -> dict[str, Any] | str:
    """Reduce a runtime ``typing`` object to a structurally comparable dict.

    Returns a sentinel string for shapes the analyzer doesn't model
    (e.g. ``Callable``, ``Literal``, multi-type unions). The harness skips
    annotations that normalize to a sentinel; they aren't comparable.
    """
    # None / type(None) — canonicalize: void doesn't carry is_optional
    # (the analyzer reports None-returns as ``is_optional=True``; runtime as
    # ``False``. Both are right, the convention just differs. Drop the field
    # for void so this isn't a false divergence.)
    if t is None or t is type(None):
        return {"kind": "void", "name": "None"}

    # PEP 604 union: types.UnionType
    if isinstance(t, types.UnionType):
        return _normalize_union(get_args(t))

    origin = get_origin(t)
    args = get_args(t)

    # typing.Union / typing.Optional
    if origin is typing.Union:
        return _normalize_union(args)

    # Annotated[T, ...]
    if origin is typing.Annotated:
        return _normalize_runtime(args[0])

    # list / Sequence / Iterable — propagate UNSUPPORTED from the element
    # type so that ``list[TypeVar]`` etc. is reported as oracle_error (out
    # of scope), not as a divergence to triage.
    if origin in (list, collections.abc.Sequence, collections.abc.Iterable):
        if not args:
            return "UNSUPPORTED:bare-sequence"
        element = _normalize_runtime(args[0])
        if isinstance(element, str):
            return f"UNSUPPORTED:list-of:{element}"
        return {
            "kind": "list",
            "name": "list",
            "is_optional": False,
            "element_type": element,
        }

    # tuple — partial: only homogeneous tuple[T, ...] maps to list-like
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        element = _normalize_runtime(args[0])
        if isinstance(element, str):
            return f"UNSUPPORTED:tuple-of:{element}"
        return {
            "kind": "list",
            "name": "list",
            "is_optional": False,
            "element_type": element,
        }

    # typing.Any — runtime erasure of Callable/Iterable/LiteralString/etc.
    # ends up here. We can't meaningfully compare against it.
    if t is typing.Any:
        return "UNSUPPORTED:Any"

    # Bare classes
    if isinstance(t, type):
        if t in (str, int, float, bool, bytes):
            return {"kind": "primitive", "name": t.__name__, "is_optional": False}
        return {"kind": "object", "name": t.__name__, "is_optional": False}

    # TypeVars, ParamSpec, Concatenate, Callable, Literal, etc. — out of scope
    return f"UNSUPPORTED:{type(t).__name__}:{t!r}"


def _normalize_union(args: tuple) -> dict[str, Any] | str:
    non_none = [a for a in args if a is not type(None)]
    has_none = any(a is type(None) for a in args)
    if not non_none:
        return {"kind": "void", "name": "None", "is_optional": False}
    if len(non_none) == 1:
        inner = _normalize_runtime(non_none[0])
        if isinstance(inner, str):  # sentinel propagates
            return inner
        return {**inner, "is_optional": has_none or inner.get("is_optional", False)}
    return f"UNSUPPORTED:multi-union:{args!r}"


def _normalize_resolved(rt: ResolvedType) -> dict[str, Any]:
    """Reduce an analyzer ``ResolvedType`` to the same shape as ``_normalize_runtime``."""
    if rt.kind == "void":
        # Match _normalize_runtime — void is canonical, no is_optional carried.
        return {"kind": "void", "name": rt.name}
    out: dict[str, Any] = {
        "kind": rt.kind,
        "name": rt.name,
        "is_optional": rt.is_optional,
    }
    if rt.element_type is not None:
        out["element_type"] = _normalize_resolved(rt.element_type)
    return out


# Test files known to fail on import (intentional runtime errors,
# experimental features, missing third-party deps). Keys are file stems;
# values are short reasons surfaced in the skip message.
_KNOWN_IMPORT_FAILURES: dict[str, str] = {}


@dataclasses.dataclass
class _AnnotationCheck:
    """Outcome of comparing one annotation between analyzer and oracle."""

    corpus: str
    file: str
    callable_name: str
    arg_name: str
    status: str  # ok | rejected | oracle_error | divergence | analyzer_error
    detail: str = ""


def _check_callable(
    corpus: str,
    file: Path,
    func: ast.FunctionDef,
    runtime_obj: Any,
    resolver: TypeResolver,
) -> list[_AnnotationCheck]:
    """Compare every annotated parameter (and the return) of one callable."""
    checks: list[_AnnotationCheck] = []
    try:
        runtime_hints = typing.get_type_hints(runtime_obj, include_extras=True)
    except Exception as e:  # noqa: BLE001 — the oracle itself failed
        checks.append(
            _AnnotationCheck(
                corpus=corpus,
                file=file.name,
                callable_name=func.name,
                arg_name="<get_type_hints>",
                status="oracle_error",
                detail=f"{type(e).__name__}: {e}",
            )
        )
        return checks

    args_with_anno = [a for a in func.args.args if a.annotation is not None]
    if func.returns is not None:
        args_with_anno.append(
            ast.arg(arg="return", annotation=func.returns, type_comment=None)
        )

    for arg in args_with_anno:
        runtime_t = runtime_hints.get(arg.arg, _MISSING)
        if runtime_t is _MISSING:
            # Oracle didn't include this name (typevar-only param, etc.)
            continue
        runtime_norm = _normalize_runtime(runtime_t)
        if isinstance(runtime_norm, str):  # UNSUPPORTED sentinel
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=file.name,
                    callable_name=func.name,
                    arg_name=arg.arg,
                    status="oracle_error",
                    detail=runtime_norm,
                )
            )
            continue

        try:
            resolved = resolver.resolve(arg.annotation)
        except TypeResolutionError as e:
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=file.name,
                    callable_name=func.name,
                    arg_name=arg.arg,
                    status="rejected",
                    detail=str(e),
                )
            )
            continue
        except Exception as e:  # noqa: BLE001
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=file.name,
                    callable_name=func.name,
                    arg_name=arg.arg,
                    status="analyzer_error",
                    detail=f"{type(e).__name__}: {e}",
                )
            )
            continue

        analyzer_norm = _normalize_resolved(resolved)
        if analyzer_norm != runtime_norm:
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=file.name,
                    callable_name=func.name,
                    arg_name=arg.arg,
                    status="divergence",
                    detail=f"analyzer={analyzer_norm!r} runtime={runtime_norm!r}",
                )
            )
        else:
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=file.name,
                    callable_name=func.name,
                    arg_name=arg.arg,
                    status="ok",
                )
            )

    return checks


_MISSING = object()


@pytest.fixture(scope="session")
def _all_checks() -> list[_AnnotationCheck]:
    """Run the differential once per session and cache the per-annotation outcomes.

    Iterates over every (corpus, file) pair declared in ``CORPORA``.
    Aggregated counts are reported by ``test_baseline_summary``;
    per-divergence failures by ``test_no_divergences``.
    """
    checks: list[_AnnotationCheck] = []
    for corpus, path in _corpus_files():
        if path.stem in _KNOWN_IMPORT_FAILURES:
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=path.name,
                    callable_name="<module>",
                    arg_name="<import>",
                    status="oracle_error",
                    detail=_KNOWN_IMPORT_FAILURES[path.stem],
                )
            )
            continue
        try:
            module = _import_from_path(path)
        except BaseException as e:  # noqa: BLE001 — some files raise SyntaxError, NameError, etc.
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=path.name,
                    callable_name="<module>",
                    arg_name="<import>",
                    status="oracle_error",
                    detail=f"import failed: {type(e).__name__}: {e}",
                )
            )
            continue

        source = path.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            checks.append(
                _AnnotationCheck(
                    corpus=corpus,
                    file=path.name,
                    callable_name="<module>",
                    arg_name="<parse>",
                    status="analyzer_error",
                    detail=f"parse failed: {e}",
                )
            )
            continue

        resolver = _build_resolver_for(tree)
        for func in _iter_top_level_callables(tree):
            runtime_obj = getattr(module, func.name, None)
            if runtime_obj is None:
                continue
            checks.extend(_check_callable(corpus, path, func, runtime_obj, resolver))

    return checks


def test_baseline_summary(_all_checks: list[_AnnotationCheck]) -> None:
    """Print per-corpus, per-status counts so baselines are visible in CI logs.

    Always passes — it's the readout. Per-divergence failures come from
    ``test_no_divergences``.
    """
    print()
    by_corpus: dict[str, dict[str, int]] = {}
    for c in _all_checks:
        by_corpus.setdefault(c.corpus, {})[c.status] = (
            by_corpus.setdefault(c.corpus, {}).get(c.status, 0) + 1
        )
    statuses = ("ok", "rejected", "oracle_error", "analyzer_error", "divergence")
    for corpus, counts in sorted(by_corpus.items()):
        total = sum(counts.values())
        print(f"=== {corpus} ({total} annotations checked) ===")
        for status in statuses:
            print(f"  {status:>16s}: {counts.get(status, 0):>5d}")


def test_no_divergences(_all_checks: list[_AnnotationCheck]) -> None:
    """Fail listing every annotation where the analyzer disagrees with typing.

    These are the bugs the corpora are meant to surface.
    Triage each: is the analyzer wrong (fix parser.py / resolver.py),
    is the harness normalization wrong (fix _normalize_runtime), or is
    the pattern out of scope (extend ``_KNOWN_IMPORT_FAILURES`` or the
    rejected-pattern coverage in resolver.py)?
    """
    divergences = [c for c in _all_checks if c.status == "divergence"]
    if not divergences:
        return
    lines = [f"{len(divergences)} divergences:"]
    for c in divergences[:50]:  # cap output so failure logs stay readable
        lines.append(f"  [{c.corpus}] {c.file}::{c.callable_name}::{c.arg_name}")
        lines.append(f"    {c.detail}")
    if len(divergences) > 50:
        lines.append(f"  ... and {len(divergences) - 50} more")
    pytest.fail("\n".join(lines))


def test_no_unexpected_analyzer_errors(_all_checks: list[_AnnotationCheck]) -> None:
    """Fail listing every annotation where the analyzer crashed (not a clean rejection).

    A clean ``TypeResolutionError`` is fine — it means the analyzer
    knows it can't handle the pattern. An uncaught exception means the
    analyzer hit an unanticipated input shape.
    """
    errors = [c for c in _all_checks if c.status == "analyzer_error"]
    if not errors:
        return
    lines = [f"{len(errors)} analyzer crashes:"]
    for c in errors[:50]:
        lines.append(f"  [{c.corpus}] {c.file}::{c.callable_name}::{c.arg_name}")
        lines.append(f"    {c.detail}")
    if len(errors) > 50:
        lines.append(f"  ... and {len(errors) - 50} more")
    pytest.fail("\n".join(lines))
