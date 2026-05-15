# Curated subset of jedi's pep0484_typing.py.
#
# Source: github.com/davidhalter/jedi @ 3102215478fe07b965dcd8221c17436d1dd7e8ac
# Path: test/completion/pep0484_typing.py
# License: MIT (see LICENSE in this directory)
#
# Why a curated subset and not a verbatim vendor:
# Jedi's full test file contains intentional incomplete-syntax markers
# (`y.` standalone, `x.setd` partial-attribute) used by their custom
# completion-test runner. Those are not standalone-importable Python,
# so the file fails both at parse time and import time.
#
# This file extracts the sections that ARE standalone-importable and
# directly relevant to the AST analyzer's bug class: TypeAlias,
# Optional, Union/PEP 604 union shapes, forward references. Each
# function below is structured for our differential harness — top-level
# def with annotated parameters, no inline jedi `#?` markers needed.

from __future__ import annotations

import typing
from typing import Optional, Tuple, TypeAlias, Union


class B:
    """A class used as a forward-referenced type."""


# ---------------------------------------------------------------------------
# TypeAlias — declarative form (PEP 613). Originally jedi tests at
# pep0484_typing.py:593-607. Exercises ``Alias`` resolved to ``int``
# both in bare position and in compound expressions.
# ---------------------------------------------------------------------------

IntX: typing.TypeAlias = int
IntY: TypeAlias = int


def f_typealias(x: IntX, y: IntY) -> int: ...


def f_typealias_optional(x: Optional[IntX], y: IntY | None) -> Optional[int]: ...


def f_typealias_in_list(x: list[IntX], y: list[IntY | None]) -> list[int]: ...


# ---------------------------------------------------------------------------
# Optional / Union — adapted from jedi pep0484_typing.py:177-201. Only
# single-non-None Union forms (Dagger doesn't support multi-type unions;
# those would surface as oracle_error in the harness).
# ---------------------------------------------------------------------------


def f_union_single(p: Union[int]) -> int: ...


def f_union_with_none(t: Union[int, None]) -> Union[int, None]: ...


def f_optional(p: Optional[int]) -> Optional[int]: ...


# ---------------------------------------------------------------------------
# Tuple — adapted from jedi pep0484_typing.py:75-99. Only the homogeneous
# variadic form (``Tuple[T, ...]``) maps cleanly to a Dagger list-type.
# ---------------------------------------------------------------------------


def f_tuple_homogeneous(r: Tuple[B, ...]) -> Tuple[int, ...]: ...


# ---------------------------------------------------------------------------
# Forward references mixed with Optional. Adapted shape from jedi's
# Sequence patterns at pep0484_typing.py:11-18 — we test the resolution
# chain (forward ref inside Optional/list).
# ---------------------------------------------------------------------------


def f_forwardref_in_optional(x: Optional["B"]) -> Optional["B"]: ...


def f_forwardref_in_list(x: list["B"]) -> list["B"]: ...
