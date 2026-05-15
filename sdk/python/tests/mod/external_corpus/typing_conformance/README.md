# Python Typing Conformance Suite (vendored)

This directory contains a vendored copy of the
[Python typing conformance suite](https://github.com/python/typing/tree/main/conformance),
maintained by the Python typing community to validate static type checkers
against the [Python typing spec](https://typing.python.org/en/latest/spec/).

## Why it's here

The Dagger Python SDK's AST analyzer (`dagger/mod/_analyzer/`) reproduces the
semantics of `typing.get_type_hints` against AST nodes rather than runtime
objects. This conformance suite is the same corpus that pyright, mypy, pyre,
and ty publish conformance scores against. Running it through our differential
test harness lets us measure how closely the analyzer matches the typing
spec, and pins regressions.

## Source

- Repository: `github.com/python/typing`
- Pinned commit: `81b183cda6aae486920a0c58f6f51c0f5315ad72`
- Pinned date: 2026-05-10
- Path inside upstream: `conformance/tests/`

## License

PSF License — see `LICENSE` in this directory.

## Updating

To re-pin to a newer upstream commit:

```sh
git clone --depth 1 https://github.com/python/typing.git /tmp/python_typing
cp -r /tmp/python_typing/conformance/tests/* sdk/python/tests/mod/external_corpus/typing_conformance/tests/
cp /tmp/python_typing/LICENSE sdk/python/tests/mod/external_corpus/typing_conformance/LICENSE
# Update the pinned commit hash above and rerun the harness
```

## What's NOT vendored

Only `conformance/tests/` is vendored. The upstream repo also has:
- `conformance/results/` — historical type-checker scores. Not relevant.
- `conformance/scripts/` — runners for type checkers. We use our own harness.
- `conformance/src/` — orchestration code for the upstream conformance run.

The `# E:` and `# E?:` comment markers inside test files are upstream's
diagnostic-expectation syntax for type checkers. Our harness ignores them —
we are not a type checker, we extract types. We assert per-annotation
equivalence with `typing.get_type_hints`, not diagnostic conformance.
