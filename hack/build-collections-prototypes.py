#!/usr/bin/env python3
"""Build the measured, experimental Dang + TypeScript changes in a new directory."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess


def run(args, *, cwd, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE).stdout


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="new build directory (must not already exist)")
    parser.add_argument("--sdk-dir", required=True, type=Path,
                        help="original greetings-api frontend SDK directory; read only")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    sdk = args.sdk_dir.resolve()
    original_core = sdk / "core.js"
    # This is a reproduction of one measured bundle, not a general JS rewriter.
    expected = "40eb66e20829d81c7fdfc87bec574301a999a93b52c2e371353f42d73936d7b0"
    if sha256(original_core) != expected:
        parser.error("SDK bundle differs from the measured input; regenerate/revalidate the experiment first")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence = repo / "hack/collections-qa-performance-data"

    module = json.loads(run(["go", "mod", "download", "-json",
                             "github.com/vito/dang/v2@v2.1.4"], cwd=repo))
    dang = output / "dang"
    shutil.copytree(module["Dir"], dang)
    for path in dang.rglob("*"):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    run(["git", "apply", str(evidence / "syntax-cache/dang-syntax-cache-prototype.patch")], cwd=dang)

    source = repo / "core/sdk/dang/v2/helpers.go"
    helper = source.read_text()
    if helper.count("dang.ParseFile(") != 2:
        raise RuntimeError("engine parser call sites changed; revalidate the overlay")
    overlay_source = output / "helpers.go"
    overlay_source.write_text(helper.replace("dang.ParseFile(", "dang.ParseFileCached("))
    overlay = output / "overlay.json"
    overlay.write_text(json.dumps({"Replace": {str(source): str(overlay_source)}}) + "\n")

    modfile = output / "engine.mod"
    shutil.copyfile(repo / "go.mod", modfile)
    shutil.copyfile(repo / "go.sum", output / "engine.sum")
    run(["go", "mod", "edit", "-modfile=" + str(modfile),
         "-replace=github.com/vito/dang/v2=" + str(dang)], cwd=repo)
    env = dict(os.environ, CGO_ENABLED="0")
    for package, name in [("./cmd/engine", "engine"), ("./cmd/dagger", "dagger")]:
        print("Building " + name, flush=True)
        run(["go", "build", "-buildvcs=false", "-modfile=" + str(modfile),
             "-overlay=" + str(overlay), "-o", str(output / name), package], cwd=repo, env=env)

    sdk_output = output / "sdk"
    shutil.copytree(sdk, sdk_output)
    core = original_core.read_text()
    assert core.count('import("http")') == core.count('import("https")') == 2
    core = core.replace('import("http")', '__daggerImportHttp()')
    core = core.replace('import("https")', '__daggerImportHttps()')
    core += '\nimport { importHttp as __daggerImportHttp, importHttps as __daggerImportHttps } from "./core-node-imports.js";\n'
    (sdk_output / "core.js").write_text(core)
    (sdk_output / "core-node-imports.js").write_text(
        'export const importHttp = () => import("http");\n'
        'export const importHttps = () => import("https");\n')
    manifest = {
        "experimental": True,
        "dagger_commit": run(["git", "rev-parse", "HEAD"], cwd=repo).strip(),
        "dang_version": "v2.1.4",
        "dang_module_sum": module["Sum"],
        "dang_patch_sha256": sha256(evidence / "syntax-cache/dang-syntax-cache-prototype.patch"),
        "sdk_input_sha256": expected,
        "outputs_sha256": {name: sha256(output / name) for name in
                           ["engine", "dagger", "sdk/core.js", "sdk/core-node-imports.js"]},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Built experimental engine/CLI and SDK in " + str(output))


if __name__ == "__main__":
    main()
