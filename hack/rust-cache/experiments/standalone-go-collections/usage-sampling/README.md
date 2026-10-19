# Standalone benefit and cost controls

The main samples and controls use identical fixtures on both sides. The candidate changes only this proposal's production files. `samples.json` contains all benefit samples; `controls/samples.json` contains all cost-control samples. `source.json` records the source version, and `reproduction.json` maps every benchmark and production file into a clean main checkout.

With Go 1.26.6 and a clean checkout of the pinned main, run:

```sh
python3 reproduce.py --checkout /path/to/main
python3 reproduce.py --checkout /path/to/main --control
```

Each command builds two test binaries and runs four alternating pairs. Compilation and fixture setup are excluded from the reported ns/op. It writes raw logs to a new temporary directory. It does not start or reset an engine. The original overlays, commands and raw logs are retained alongside the portable reproduction script.

These component measurements do not establish a complete Go listing gain. Tests on the source branch separately check correctness with the race detector.
