# Pyright Test Samples (vendored, focused subset)

Vendored copy of selected `.py` files from
[microsoft/pyright](https://github.com/microsoft/pyright)'s test samples,
used as type-resolution corpus for the Dagger Python SDK's AST analyzer
differential test (`test_external_corpus.py`).

## Why this is here, in addition to the typing conformance suite

The typing conformance suite is checker-flavored — it tests that type checkers
produce specific *diagnostics* for spec-defined patterns. Pyright's samples
are checker-flavored too, but they're far more diverse: 1,288 standalone
files written over ~6 years to exercise specific bugs and edge cases as
pyright's authors discovered them. In particular, pyright's
`recursiveTypeAlias12.py` contains the exact resolution pattern that PR
#13149 fixed in our analyzer (`Alias: TypeAlias = …; def f(x: Alias | None)`)
— the conformance suite does not.

This vendor mines the pile for files most likely to exercise the analyzer's
bug class: type aliases, Annotated, Self, forward refs, Optional/Union,
inheritance, generics, protocols. ~150 files.

## Source

- Repository: `github.com/microsoft/pyright`
- Pinned commit: `b13157b0fac479f12ca1a4c0881652769f533f27`
- Pinned date: 2026-05-12
- Path inside upstream: `packages/pyright-internal/src/tests/samples/`

Patterns vendored: `typeAlias*.py`, `alias*.py`, `annotated*.py`,
`annotatedVar*.py`, `self*.py`, `forward*.py`, `optional*.py`, `union*.py`,
`newType*.py`, `inheritance*.py`, `protocol*.py`, `genericType*.py`.

## License

MIT — see `LICENSE` in this directory.

## Updating

To re-pin to a newer upstream commit:

```sh
git clone --depth 1 https://github.com/microsoft/pyright.git /tmp/pyright
SRC=/tmp/pyright/packages/pyright-internal/src/tests/samples
DST=sdk/python/tests/mod/external_corpus/pyright_samples
rm -f $DST/*.py
for pat in typeAlias alias annotated annotatedVar self forward \
           optional union newType inheritance protocol genericType; do
  ls $SRC | grep -E "^${pat}[0-9]?[0-9]?\.py$" | xargs -I{} cp $SRC/{} $DST/
done
cp /tmp/pyright/LICENSE.txt $DST/LICENSE
# Update the pinned commit hash above
```

## Caveat

Pyright samples often contain inline error markers (`# This should generate
an error...`) and patterns specifically designed to trigger checker
diagnostics. Our harness ignores the markers — it asserts per-annotation
equivalence with `typing.get_type_hints`. Patterns where typing itself
fails to resolve (intentional runtime errors, undefined references) are
recorded as `oracle_error` and skipped automatically.
