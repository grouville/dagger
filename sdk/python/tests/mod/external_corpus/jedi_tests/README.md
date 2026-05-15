# Jedi Test Fixtures (curated subset)

A hand-curated subset of jedi's `pep0484_typing.py`. Used as a third
corpus in the AST analyzer differential test (`test_external_corpus.py`).

## Why a curated subset, not a verbatim vendor

Jedi's full test file contains intentional incomplete-syntax markers
(`y.` standalone, `x.setd` partial-attribute) used by jedi's own custom
completion-test runner. These aren't valid standalone Python, so the
file fails both at parse time and import time. ~47 lines need
sanitization to even reach module-import; even after that, the file
still fails on incomplete-attribute references like `TestDict.setd`.

Rather than fight the format, this directory holds a curated subset of
the standalone-importable sections most relevant to Dagger's bug class:
TypeAlias, Optional, Union/PEP 604 union shapes, forward references.

## Source

- Repository: `github.com/davidhalter/jedi`
- Pinned commit: `3102215478fe07b965dcd8221c17436d1dd7e8ac`
- Pinned date: 2026-05-02
- Path inside upstream: `test/completion/pep0484_typing.py`

## License

MIT — see `LICENSE` in this directory.
