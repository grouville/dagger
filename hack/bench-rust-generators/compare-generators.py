#!/usr/bin/env python3
"""Fixture-specific standalone generate A/B with an ordinary Cargo reference.

Requires --execute. Creates only owned temporary source copies and one labeled
native-control container; never resets either Dagger engine. Retains all source,
output, logs and timing evidence, including failures and permission discrepancies.
No profiler/analyzer is run here. Audit actual execution in captured OTel offline.
"""

import argparse
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import stat
import statistics
import subprocess
import tempfile
import time
import tomllib
import uuid
from urllib.parse import parse_qs, urlparse


IMAGE = "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b"
SIDES = ("before", "after", "native")
ORDERS = tuple(itertools.permutations(SIDES))
FLAGS = ["--workspace", "--locked", "--message-format=json-render-diagnostics"]
EDITS = {"application": ("app/src/main.rs", '"app-v1: {}"'),
         "library": ("library/src/lib.rs", '"hello from the library"')}
OUTPUTS = {"debug/prototype-app", "debug/prototype-secondary",
           "debug/libprototype_library.rlib", "debug/libprototype_library.a"}
OWNER_LABEL = "dagger.rust.generator-bench-owner"
ARCHIVES = {"debug/libprototype_library.a", "debug/libprototype_library.rlib"}
RCGU_NAME = re.compile(r"^(prototype_library-[0-9a-f]{16}\.[a-z0-9]+\.)([a-z0-9]{7})(\.rcgu\.o)$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def append_json(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(value) + "\n")


def source_manifest(root):
    result = {}
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in {"target", ".git"})
        for name in dirs + sorted(files):
            path = Path(directory) / name
            require(not path.is_symlink(), f"unsupported fixture symlink: {path}")
        for name in sorted(files):
            if name in {"dagger.toml", "dagger.lock"} and Path(directory) == root:
                continue
            path = Path(directory) / name
            require(path.is_file(), f"non-file source: {path}")
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def edited(original, scenario, token):
    require(re.fullmatch(r"[a-z0-9-]+", token), "unsafe edit token")
    anchor = EDITS[scenario][1]
    require(original.count(anchor) == 1, f"expected one {scenario} edit anchor")
    replacement = '"app-' + token + ': {}"' if scenario == "application" else '"library-' + token + '"'
    return original.replace(anchor, replacement)


def cargo_artifacts(log, workspace_members):
    """Inspect captured Cargo JSON, not stderr compilation lines or exec proof."""
    artifacts = {}
    finished = False
    for line in log.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get("reason") == "build-finished":
            require(message.get("success") is True, "Cargo reported unsuccessful build")
            finished = True
        if message.get("reason") != "compiler-artifact" or message.get("package_id") not in workspace_members:
            continue
        target = message["target"]
        if "custom-build" in target["kind"]:
            continue
        require(isinstance(message.get("fresh"), bool), "Cargo freshness must be boolean")
        require(message["profile"]["opt_level"] == "0" and message["profile"]["debuginfo"] == 2,
                "fixture must retain normal full debug Cargo profile")
        for filename in message["filenames"]:
            require(filename.startswith(("/out/", "/build/")), f"unexpected Cargo output: {filename}")
            if not filename.startswith("/out/"):
                continue
            relative = filename[len("/out/"):]
            require(relative and all(part not in {"", ".", ".."} for part in relative.split("/")),
                    f"non-canonical output: {filename}")
            entry = dict(package_id=message["package_id"], target=target["name"], fresh=message["fresh"])
            require(relative not in artifacts or artifacts[relative] == entry, f"conflicting output: {relative}")
            artifacts[relative] = entry
    require(finished, "missing successful Cargo build-finished record")
    require(set(artifacts) == OUTPUTS, f"unexpected selected output set: {sorted(artifacts)}")
    return artifacts


def artifact_manifest(root, selected, exact):
    result = {}
    require(root.is_dir() and not root.is_symlink(), f"artifact root must be a real directory: {root}")
    for relative in sorted(selected):
        require(relative and all(part not in {"", ".", ".."} for part in relative.split("/")), "invalid artifact path")
        path = root / relative
        for parent in path.parents:
            if parent == root:
                break
            require(parent.is_dir() and not parent.is_symlink(), f"artifact parent must be a real directory: {parent}")
        attrs = path.lstat()
        require(stat.S_ISREG(attrs.st_mode), f"artifact must be regular: {path}")
        result[relative] = dict(kind="file", bytes=attrs.st_size, sha256=digest(path),
                                mode=stat.S_IMODE(attrs.st_mode))
    if exact:
        actual = set()
        for directory, dirs, files in os.walk(root):
            for name in dirs:
                require(not (Path(directory) / name).is_symlink(), "artifact directory symlink")
            actual.update((Path(directory) / name).relative_to(root).as_posix() for name in files)
        require(actual == set(selected), f"unexpected generated target set: {actual ^ set(selected)}")
    return result


def inspect_archive(path, ar):
    """Read with GNU ar; do not parse archive indexes, headers or string tables ourselves."""
    raw = path.read_bytes()
    require(raw.startswith(b"!<arch>\n"), "expected an ordinary archive, not a thin archive")
    env = dict(os.environ, LC_ALL="C", TZ="UTC")

    def read(option):
        result = subprocess.run([ar, option, str(path)], env=env, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(not result.stderr, f"ar {option} reported a diagnostic: {result.stderr!r}")
        return result.stdout

    names = read("t").decode("ascii").splitlines()
    rows = read("tv").decode("ascii").splitlines()
    require(names and len(names) == len(set(names)) == len(rows), "duplicate/missing archive members")
    headers = []
    for name, row in zip(names, rows):
        require(re.fullmatch(r"[A-Za-z0-9_.+-]+", name), f"unsupported archive member name: {name}")
        header, reported = row.rsplit(" ", 1)
        fields = header.split()
        require(reported == name and len(fields) == 7 and fields[2].isdigit(), "unexpected GNU ar member table")
        headers.append(fields)
    # ar p emits ordinary member payloads in table order, excluding its index
    # and long-name table. The full-archive comparison below checks those too.
    payload = read("p")
    require(sum(int(header[2]) for header in headers) == len(payload), "archive member sizes do not match ar output")
    members = []
    offset = 0
    for name, header in zip(names, headers):
        size = int(header[2])
        members.append(dict(name=name, header=header, payload=payload[offset:offset + size]))
        offset += size
    require(digest(path) == hashlib.sha256(raw).hexdigest(), "archive changed while being inspected")
    return dict(raw=raw, members=members)


def archive_equivalence(actual, reference, suffix):
    """Permit only this fixture's independent rustc codegen-member identifiers.

    This is an audit of copies in memory, never a rewrite of published files.
    Crate hash, CGU identity, member order, all headers and all object bytes stay
    exact. rlib link metadata may refer to the renamed member; nothing else may.
    """
    require(suffix in {".a", ".rlib"}, "unsupported archive kind")
    left, right = actual["members"], reference["members"]

    def key(name):
        return RCGU_NAME.sub(r"\1<CODEGEN-ID>\3", name)

    keys = [[key(member["name"]) for member in members] for members in (left, right)]
    require(keys[0] == keys[1] and len(set(keys[0])) == len(keys[0]), "archive member names/order differ or collide")
    require([item["header"] for item in left] == [item["header"] for item in right], "archive member headers differ")
    mapping = {a["name"].encode(): b["name"].encode() for a, b in zip(left, right) if a["name"] != b["name"]}
    require(mapping and len(set(mapping.values())) == len(mapping), "missing or colliding compiler-name mapping")
    require(not set(mapping).intersection(mapping.values()), "ambiguous compiler-name replacement")
    expected_members = 1 if suffix == ".rlib" else 2
    require(sum(RCGU_NAME.fullmatch(item["name"]) is not None for item in left) == expected_members,
            "unexpected number of fixture codegen members")
    require(sum(item["name"] == "lib.rmeta-link" for item in left) == (suffix == ".rlib"), "unexpected rlib link metadata")

    def mapped(value):
        for old, new in mapping.items():
            require(len(old) == len(new), "compiler-name lengths differ")
            value = value.replace(old, new)
        return value

    members = []
    for a, b in zip(left, right):
        content = a["payload"]
        if a["name"] == "lib.rmeta-link":
            for old, new in mapping.items():
                require(content.count(old) == b["payload"].count(new) == 1, "unexpected compiler-name references in rlib metadata")
            require(mapped(content) == b["payload"], "rlib metadata differs beyond compiler-member references")
        else:
            require(content == b["payload"], f"archive member payload differs: {a['name']}")
        members.append(dict(actual_name=a["name"], reference_name=b["name"], bytes=len(content),
                            raw_payload_equal=content == b["payload"],
                            actual_sha256=hashlib.sha256(content).hexdigest(),
                            reference_sha256=hashlib.sha256(b["payload"]).hexdigest()))

    occurrences = 2 if suffix == ".rlib" else 1
    for old, new in mapping.items():
        require(actual["raw"].count(old) == reference["raw"].count(new) == occurrences,
                "unexpected compiler-name occurrences in archive")
    # This additionally rejects changed symbols/index offsets, header bytes,
    # padding, extra data, and anything ar p does not expose. Exact code-payload
    # checks above prevent this mapping from hiding an object-content change.
    require(mapped(actual["raw"]) == reference["raw"], "archive bytes differ beyond exact compiler-member names")
    return dict(equivalent=True, raw_bytes_equal=False,
                policy="exact archive except verified compiler-generated member identifiers",
                renamed_members=[dict(actual=old.decode(), reference=new.decode()) for old, new in mapping.items()],
                members=members, index_headers_padding_equal=True)


def compare_artifacts(manifests, archive_roots=None, archive_audits=None, ar="ar"):
    discrepancies = []
    archive_audits = [] if archive_audits is None else archive_audits
    inspected = {}
    native = manifests["native"]
    for side in ("before", "after"):
        require(set(manifests[side]) == set(native), f"{side} target set differs")
        for name, expected in native.items():
            actual = manifests[side][name]
            require(all(actual[key] == expected[key] for key in ("kind", "bytes")),
                    f"{side} artifact size/type differs: {name}")
            if actual["sha256"] != expected["sha256"]:
                require(name in ARCHIVES and archive_roots is not None, f"{side} artifact bytes/type differ: {name}")
                audit = dict(side=side, path=name, equivalent=False, raw_bytes_equal=False,
                             actual_sha256=actual["sha256"], reference_sha256=expected["sha256"])
                archive_audits.append(audit)
                try:
                    for owner in (side, "native"):
                        if (owner, name) not in inspected:
                            value = inspect_archive(archive_roots[owner] / name, ar)
                            require(hashlib.sha256(value["raw"]).hexdigest() == manifests[owner][name]["sha256"],
                                    "archive changed since artifact manifest")
                            inspected[owner, name] = value
                    audit.update(archive_equivalence(inspected[side, name], inspected["native", name], Path(name).suffix))
                except Exception as error:
                    audit["error"] = str(error)
                    raise
            elif name in ARCHIVES:
                archive_audits.append(dict(side=side, path=name, equivalent=True, raw_bytes_equal=True,
                                          actual_sha256=actual["sha256"], reference_sha256=expected["sha256"]))
            if actual["mode"] != expected["mode"]:
                known = side == "before" and (expected["mode"], actual["mode"]) in {(0o755, 0o777), (0o644, 0o666)}
                discrepancies.append(dict(side=side, path=name, native=oct(expected["mode"]),
                    actual=oct(actual["mode"]), known_baseline_bug=known))
    return discrepancies


def verify_native_owner(identity, native_id, nonce):
    require(identity.get("Id") == native_id and
            identity.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == nonce,
            "refusing cleanup: native ownership changed")


def validate_mode_discrepancies(discrepancies, allow_known_baseline=True):
    if not allow_known_baseline:
        require(not discrepancies, "CLI comparison requires exact native permissions on both sides")
    require(all(item["known_baseline_bug"] for item in discrepancies),
            "unrecognized permission discrepancy; raw evidence retained, outputs were not normalized")


def isolated_git_environment(environment):
    # This is a local fixture, not an authenticated Git workflow. Inherited
    # worktree/config/template/trace variables must not redirect setup or CLI
    # discovery, and their values may contain credentials: never record them.
    clean = {key: value for key, value in environment.items() if not key.upper().startswith("GIT_")}
    removed = len(environment) - len(clean)
    clean.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    policy = dict(inherited_variables_removed=removed, global_config=os.devnull,
                  system_config_disabled=True, terminal_prompt=False,
                  note="All inherited GIT_* variables removed; values are not recorded.")
    return clean, policy


def initialize_frozen_module_git(process, frozen):
    # Dagger's local module import context is bounded by its Git root. A copied
    # module without .git can inherit a changing ancestor repository (e.g. /tmp)
    # and make a later diagnostic query execute under a different module identity.
    require(frozen.is_dir() and not frozen.is_symlink(), "frozen module must be a real directory")
    git_dir = frozen / ".git"
    require(not git_dir.exists() and not git_dir.is_symlink(), "refusing preexisting frozen module Git state")
    process("setup-module-git-init", ["git", "init", "--quiet"], cwd=frozen)
    require(git_dir.is_dir() and not git_dir.is_symlink(), "frozen module Git state must be its own real directory")
    output = process("setup-module-git-root", ["git", "-C", str(frozen), "rev-parse", "--show-toplevel"], cwd=frozen)
    roots = output.read_text().strip().splitlines()
    require(len(roots) == 1 and Path(roots[0]).is_absolute(), "invalid frozen module Git root output")
    observed = Path(roots[0]).resolve(strict=True)
    require(observed == frozen.resolve(strict=True), "frozen module Git root does not match its directory")
    return str(observed)


def initialize_generator_workspaces(process):
    # Host-side Changeset export requires a Git workspace, even though .git is
    # intentionally excluded from the container's Cargo source input.
    for side in ("before", "after"):
        process("setup-" + side + "-git-init", ["git", "init", "--quiet"], side)


def comparison_engine_name(runner):
    # This mode is a local Docker fixture, not a general runner-identity API.
    parsed = urlparse(runner)
    options = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    require(parsed.scheme == "docker-image" and parsed.netloc and not parsed.fragment,
            "CLI comparison requires an explicit docker-image runner")
    require(parsed.username is None and parsed.password is None, "runner userinfo is not supported")
    require(set(options) <= {"container", "volume", "cleanup"}, "unknown runner options")
    require(all(len(values) == 1 for values in options.values()), "duplicate runner options")
    require(options.get("cleanup") == ["false"], "CLI comparison requires cleanup=false")
    names = options.get("container", [])
    require(len(names) == 1 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", names[0]),
            "CLI comparison requires an exact container name")
    if "volume" in options:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", options["volume"][0]),
                "CLI comparison requires an exact volume name")
    return names[0]


def record_comparison_engine(process, label, runner, expected_image):
    name = comparison_engine_name(runner)
    parsed = urlparse(runner)
    image_reference = parsed.netloc + parsed.path
    # A retagged image can make the CLI replace the named engine. Reject that
    # before either CLI runs, and verify the reference again at the end.
    image_log = process(label + "-image", ["docker", "image", "inspect", "--format", "{{.Id}}", image_reference], "before")
    resolved_image = image_log.read_text().strip()
    require(resolved_image == expected_image, "runner image reference does not resolve to expected image")
    # Retain only identity fields, not engine environment/configuration values.
    fields = ('{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},'
              '"Running":{{json .State.Running}},"StartedAt":{{json .State.StartedAt}},'
              '"Pid":{{json .State.Pid}},"RestartCount":{{json .RestartCount}}}')
    log = process(label, ["docker", "inspect", "--type", "container", "--format", fields, name], "before")
    row = json.loads(log.read_text())
    require(isinstance(row, dict), "expected one engine container")
    require(re.fullmatch(r"[a-f0-9]{64}", row.get("Id", "")) and row.get("Name") == "/" + name,
            "engine container identity does not match runner")
    require(row.get("Image") == expected_image, "engine image identity does not match expected image")
    require(row.get("Running") is True and row.get("StartedAt") and row.get("Pid", 0) > 0,
            "comparison engine must already be running")
    return dict(runner=runner, container_id=row["Id"], name=row["Name"], image_id=row["Image"],
                image_reference=image_reference, resolved_image_id=resolved_image,
                started_at=row["StartedAt"], pid=row["Pid"], restart_count=row.get("RestartCount"))


def select_clis(args):
    clis = {"before": args.dagger.resolve(strict=True),
            "after": (args.after_dagger if args.compare_clis else args.dagger).resolve(strict=True)}
    require(all(path.is_file() and os.access(path, os.X_OK) for path in clis.values()), "CLIs must be executable files")
    hashes = {side: digest(path) for side, path in clis.items()}
    if args.compare_clis:
        require(hashes["before"] != hashes["after"], "CLI comparison requires distinct binary hashes")
    return clis, hashes


def verify_cli_hashes(clis, hashes):
    require(all(digest(path) == hashes[side] for side, path in clis.items()), "CLI changed during run")


def verify_comparison_engine_identity(before, after):
    require(before == after, "comparison engine changed during run")


def run_dagger(process, clis, label, side, *argv, **kwargs):
    return process(label, [str(clis[side]), *argv], side, **kwargs)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dagger", required=True, type=Path)
    parser.add_argument("--compare-clis", action="store_true", help="Compare --dagger and --after-dagger on one existing engine")
    parser.add_argument("--after-dagger", type=Path, help="Candidate CLI; requires --compare-clis")
    parser.add_argument("--before-engine", required=True)
    parser.add_argument("--after-engine", required=True)
    parser.add_argument("--before-image-id")
    parser.add_argument("--after-image-id")
    parser.add_argument("--module", default=Path(__file__).parent, type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--samples", type=int, default=3, help="Pilot: 3; real comparison: 30")
    parser.add_argument("--engine-readiness", choices=("asymmetric-or-unknown", "explicitly-equally-prewarmed"),
                        default="asymmetric-or-unknown")
    parser.add_argument("--keep-native", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("refusing setup or commands without --execute")
    if args.samples < 1:
        parser.error("positive samples are required")
    if args.compare_clis:
        if args.after_dagger is None or args.before_engine != args.after_engine:
            parser.error("CLI comparison requires --after-dagger and identical before/after runner URLs")
        if not args.before_image_id or args.before_image_id != args.after_image_id or not re.fullmatch(r"sha256:[a-f0-9]{64}", args.before_image_id):
            parser.error("CLI comparison requires matching explicit engine image IDs")
        try:
            comparison_engine_name(args.before_engine)
        except ValueError as error:
            parser.error(str(error))
    elif args.after_dagger is not None:
        parser.error("--after-dagger requires explicit --compare-clis")
    elif args.before_engine == args.after_engine:
        parser.error("positive samples and distinct before/after engine URLs are required")
    return args


def main(argv=None):
    args = parse_args(argv)
    clis, cli_hashes = select_clis(args)
    cli = clis["before"]
    module = args.module.resolve(strict=True)
    fixture = (args.fixture or module / "fixtures/workspace").resolve(strict=True)
    require(tomllib.loads((fixture / "app/Cargo.toml").read_text())["package"]["name"] == "prototype-app", "wrong fixture app")
    require(tomllib.loads((fixture / "library/Cargo.toml").read_text())["lib"]["crate-type"] == ["rlib", "staticlib"], "staticlib fixture required")
    require(not any((fixture / name).exists() for name in ("rust-toolchain", "rust-toolchain.toml", ".cargo")),
            "fixture-specific default-profile comparison does not accept custom toolchain/config")
    initial_sources = source_manifest(fixture)
    originals = {scenario: (fixture / path).read_text() for scenario, (path, _) in EDITS.items()}
    for scenario, original in originals.items():
        edited(original, scenario, "validation")
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    require(urlparse(endpoint).hostname in {"localhost", "127.0.0.1", "::1"},
            "start a local OTel receiver and set OTEL_EXPORTER_OTLP_ENDPOINT for later exec auditing")
    for key, value in os.environ.items():
        if key.startswith("OTEL_EXPORTER_OTLP") and key.endswith("ENDPOINT") and value:
            require(urlparse(value).hostname in {"localhost", "127.0.0.1", "::1"}, f"non-local telemetry endpoint: {key}")
    ar = shutil.which("ar")
    require(ar is not None, "GNU ar is required for strict compiler-archive equivalence auditing")
    ar = str(Path(ar).resolve(strict=True))
    ar_version = subprocess.check_output([ar, "--version"], env=dict(os.environ, LC_ALL="C")).decode()
    require(ar_version.startswith("GNU ar "), "this fixture audit requires GNU ar table output")
    archive_tool = dict(path=ar, sha256=digest(ar), version=ar_version.strip())

    root = Path(tempfile.mkdtemp(prefix="dagger-rust-generator-pair-"))
    nonce = uuid.uuid4().hex
    print(root, flush=True)
    frozen = root / "module"
    frozen.mkdir()
    module_hashes = {}
    for name in ("main.dang", "dagger-module.toml"):
        source = module / name
        require(source.is_file() and not source.is_symlink(), f"invalid module input: {source}")
        expected = digest(source)
        shutil.copyfile(source, frozen / name)
        require(digest(frozen / name) == expected == digest(source), f"module changed during freeze: {source}")
        module_hashes[name] = expected
    workdirs = {side: root / side for side in SIDES}
    for side, workdir in workdirs.items():
        shutil.copytree(fixture, workdir, ignore=shutil.ignore_patterns(".git", "target", "dagger.toml", "dagger.lock"))
        (workdir / "target").mkdir(mode=0o755)
        (workdir / "target/dagger").mkdir(mode=0o755)
        (workdir / "target").chmod(0o755)
        (workdir / "target/dagger").chmod(0o755)
        (workdir / "target/KEEP").write_bytes(b"outside generated subtree\n")
        (workdir / "target/KEEP").chmod(0o644)  # Initial state only; never normalize generated outputs.
        if side != "native":
            (workdir / "dagger.toml").write_text(
                '[modules.rust]\nsource = ' + json.dumps(str(frozen)) + '\n[modules.rust.settings]\n' +
                'cacheKey = ' + json.dumps(f"rust-generator-{nonce}-{side}") + '\n' +
                'image = ' + json.dumps(IMAGE) + '\nlocked = true\ntracePhases = false\n' +
                'pinnedSourceSync = true\nprepareProjectToolchain = true\n' +
                'features = []\nallFeatures = false\nnoDefaultFeatures = false\n')
    env_base, git_environment = isolated_git_environment(os.environ)
    if args.compare_clis:
        # URL cleanup=false is the sole policy input for this controlled mode.
        env_base.pop("DAGGER_LEAVE_OLD_ENGINE", None)
    for key in list(env_base):
        if key.startswith("_EXPERIMENTAL_DAGGER_") or key in {
            "DAGGER_ENGINE", "DAGGER_CONFIG", "DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN",
            "DAGGER_CLOUD_TOKEN", "DAGGER_API_TOKEN", "DAGGER_CLOUD_URL", "DAGGER_API_URL", "CPUPROFILE",
            "OTEL_EXPORTER_OTLP_HEADERS", "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
            "OTEL_EXPORTER_OTLP_LOGS_HEADERS", "OTEL_EXPORTER_OTLP_METRICS_HEADERS"}:
            env_base.pop(key)
    env_base.update(DO_NOT_TRACK="1", OTEL_EXPORTER_OTLP_TRACES_LIVE="1")
    environments = {}
    for side, runner in (("before", args.before_engine), ("after", args.after_engine)):
        environments[side] = dict(env_base, DAGGER_ENGINE=runner)
        for part in ("CONFIG", "CACHE", "DATA", "STATE"):
            directory = root / "cli-state" / side / part.lower()
            directory.mkdir(parents=True)
            environments[side][f"XDG_{part}_HOME"] = str(directory)
    environments["native"] = env_base
    native_name = "dagger-rust-gen-native-" + nonce
    native_id = None
    metadata = dict(purpose="matched standalone generator edit A/B; ordinary Cargo via docker exec reference",
        status="running", cold_claim=False, samples=args.samples, native_final_outputs="persistent",
        native_wcprof=False, actual_exec_audit="required offline from captured timed-command OTel; logs are not proof",
        archive_tool=archive_tool,
        archive_policy="Raw hashes retained; differing fixture archives require exact bytes except verified compiler-member identifiers, audited outside timers",
        cli=str(cli), cli_sha256=cli_hashes["before"], script_sha256=digest(Path(__file__)),
        comparison_mode="cli" if args.compare_clis else "engine",
        clis={side: dict(path=str(path), sha256=cli_hashes[side]) for side, path in clis.items()},
        comparison_engine_identity={},
        module_source=str(module), frozen_module=str(frozen), frozen_module_hashes=module_hashes,
        moduleGitRoot=None, git_environment=git_environment,
        fixture_source=str(fixture), initial_source_hashes=initial_sources, nonce=nonce,
        workdirs={side: str(path) for side, path in workdirs.items()},
        engines={"before": args.before_engine, "after": args.after_engine},
        engine_image_ids={"before": args.before_image_id, "after": args.after_image_id},
        engine_readiness=args.engine_readiness, image=IMAGE, cargo_flags=FLAGS,
        build_dir="/build", target_dir="/out", profile="default dev; no profile/features/target/debug overrides",
        local_otel=endpoint, do_not_track=1, orders=ORDERS, setup_builds_per_side=1, warmup_triples_per_scenario=1,
        setup_note="Existing engine readiness may differ; only unique Cargo keys and equivalent recorded warmups are controlled.",
        comparison_note="Native keeps ordinary final outputs. Dagger additionally runs metadata, selects artifacts and merges/exports Changesets.",
        known_semantic_difference="Baseline can produce modes777/666 versus native/candidate755/644; never normalized silently.",
        output_history="Each side retains its own outputs; baseline permission divergence can persist into later samples and is not normalized.",
        native_container=dict(name=native_name, owner_label=OWNER_LABEL, owner=nonce))
    write_json(root / "metadata.json", metadata)
    with (root / "timings.csv").open("x") as stream:
        csv.writer(stream).writerow(["scenario", "sample", "side", "milliseconds", "warmup", "exit_code"])
    timings = []

    def process(label, command, side="native", timed=False, scenario=None, sample=None, cwd=None):
        command_cwd = workdirs[side] if cwd is None else cwd
        record = dict(label=label, command=command, side=side, cwd=str(command_cwd),
                      scenario=scenario, sample=sample, timed=timed, warmup=sample == 0, exit_code=None)
        log_path = root / (label + ".log")
        with log_path.open("xb") as log:
            record["start_unix_ns"], start = time.time_ns(), time.perf_counter_ns()
            try:
                result = subprocess.run(command, cwd=command_cwd, env=environments[side],
                                        stdout=log, stderr=subprocess.STDOUT)
                record["exit_code"] = result.returncode
            finally:
                record["milliseconds"] = (time.perf_counter_ns() - start) / 1e6
                record["end_unix_ns"] = time.time_ns()
                append_json(root / "processes.jsonl", record)
                if timed:
                    timings.append(record)
                    with (root / "timings.csv").open("a") as stream:
                        csv.writer(stream).writerow([scenario, sample, side, record["milliseconds"], sample == 0, record["exit_code"]])
        require(record["exit_code"] == 0, f"{label} failed; evidence: {log_path}")
        return log_path

    def native_command(*argv):
        return ["docker", "exec", "--workdir", "/src", native_name,
                "env", "CARGO_BUILD_BUILD_DIR=/build", "CARGO_TARGET_DIR=/out", *argv]

    def run_build(side, label, timed=False, scenario=None, sample=None):
        if side == "native":
            return process(label, native_command("cargo", "build", *FLAGS), side, timed, scenario, sample)
        return run_dagger(process, clis, label, side, "generate", "-y", timed=timed, scenario=scenario, sample=sample)

    def verify_engine_after():
        metadata["comparison_engine_identity"]["post_attempted"] = True
        identity = record_comparison_engine(process, "comparison-engine-after", args.after_engine, args.after_image_id)
        metadata["comparison_engine_identity"]["after"] = identity
        verify_comparison_engine_identity(metadata["comparison_engine_identity"]["before"], identity)

    try:
        if args.compare_clis:
            metadata["known_semantic_difference"] = "None allowed: both CLIs must preserve exact native permissions."
            metadata["output_history"] = "Each side retains its own outputs; every permission difference fails."
            metadata["comparison_engine_identity"]["before"] = record_comparison_engine(
                process, "comparison-engine-before", args.before_engine, args.before_image_id)
            for side in ("before", "after"):
                version = run_dagger(process, clis, "setup-" + side + "-cli-version", side, "version")
                metadata["clis"][side]["reported_version"] = version.read_text().strip()
            write_json(root / "metadata.json", metadata)
        metadata["moduleGitRoot"] = initialize_frozen_module_git(process, frozen)
        write_json(root / "metadata.json", metadata)
        initialize_generator_workspaces(process)
        # A generated name is not sufficient ownership proof for later cleanup.
        created = process("setup-native-create", ["docker", "create", "--name", native_name,
            "--label", OWNER_LABEL + "=" + nonce, "--platform", "linux/amd64",
            "--mount", f"type=bind,source={workdirs['native']},target=/src",
            "--mount", f"type=bind,source={workdirs['native'] / 'target/dagger'},target=/out",
            "--mount", f"type=bind,source={root},target=/bench,readonly",
            "--workdir", "/src", IMAGE, "sleep", "infinity"])
        native_id = created.read_text().strip().splitlines()[-1]
        require(re.fullmatch(r"[a-f0-9]{64}", native_id), "unexpected native container ID")
        metadata["native_container"]["id"] = native_id
        process("setup-native-start", ["docker", "start", native_id])
        process("setup-native-version", native_command("cargo", "--version"))
        workspace_metadata = process("setup-native-metadata", native_command("cargo", "metadata", "--no-deps", "--format-version=1", "--locked"))
        workspace_members = set(json.loads(workspace_metadata.read_text())["workspace_members"])
        require(len(workspace_members) == 2, "expected exactly two fixture workspace members")
        for side in SIDES:
            run_build(side, "setup-build-" + side)
        write_json(root / "metadata.json", metadata)
        expected_sources = initial_sources.copy()
        current = originals.copy()
        pair_number = 0
        discrepancies = []
        archive_comparisons = []
        for scenario, (relative, _) in EDITS.items():
            for sample in range(args.samples + 1):
                for side, workdir in workdirs.items():
                    require(source_manifest(workdir) == expected_sources, f"concurrent source change: {side}")
                token = f"{nonce}-{scenario}-{sample}"
                changed = edited(originals[scenario], scenario, token)
                for workdir in workdirs.values():
                    edit_path = workdir / relative
                    require(edit_path.resolve() == edit_path and edit_path.stat().st_nlink == 1,
                            f"refusing linked edit target: {edit_path}")
                    edit_path.write_text(changed)
                current[scenario] = changed
                expected_sources[relative] = hashlib.sha256(changed.encode()).hexdigest()
                order = ORDERS[pair_number % len(ORDERS)]
                pair_number += 1
                append_json(root / "edits.jsonl", dict(scenario=scenario, sample=sample, path=relative,
                    token=token, sha256=expected_sources[relative], order=order))
                logs = {}
                # Nothing but subprocess timers and small record writes between these three commands.
                for side in order:
                    logs[side] = run_build(side, f"{scenario}-{sample}-{side}", True, scenario, sample)
                artifacts = {}
                manifests = {}
                modes = {}
                for side in SIDES:
                    if side != "native":
                        logs[side] = run_dagger(process, clis, f"{scenario}-{sample}-{side}-messages",
                            side, "api", "call", "rust", "build-messages", "contents")
                    artifacts[side] = cargo_artifacts(logs[side].read_text(), workspace_members)
                    manifests[side] = artifact_manifest(workdirs[side] / "target/dagger", artifacts[side], side != "native")
                    require((workdirs[side] / "target/KEEP").read_bytes() == b"outside generated subtree\n", "outside sentinel bytes changed")
                    modes[side] = {}
                    for name in ("target", "target/dagger", "target/dagger/debug", "target/KEEP"):
                        attrs = (workdirs[side] / name).lstat()
                        require(stat.S_ISREG(attrs.st_mode) if name.endswith("KEEP") else stat.S_ISDIR(attrs.st_mode),
                                f"changed sentinel/ancestor type: {side}/{name}")
                        modes[side][name] = stat.S_IMODE(attrs.st_mode)
                    require(source_manifest(workdirs[side]) == expected_sources, f"source changed during build: {side}")
                # Retain raw manifests even when a validation below fails.
                audit = dict(scenario=scenario, sample=sample, artifacts=artifacts, manifests=manifests, ancestor_modes=modes)
                append_json(root / "artifact-audits.jsonl", audit)
                require(artifacts["before"] == artifacts["after"] == artifacts["native"], "Cargo target/freshness differs")
                nonfresh = {entry["target"] for entry in artifacts["native"].values() if not entry["fresh"]}
                expected_dirty = {"prototype-app"} if scenario == "application" else {"prototype_library", "prototype-app", "prototype-secondary"}
                require(nonfresh == expected_dirty, f"unexpected dirty targets: {nonfresh}")
                archive_audits = []
                try:
                    delta = compare_artifacts(manifests,
                        {side: path / "target/dagger" for side, path in workdirs.items()}, archive_audits, ar)
                finally:
                    append_json(root / "archive-equivalence.jsonl", dict(scenario=scenario, sample=sample,
                        archives=archive_audits, artifacts_modified=False))
                archive_comparisons.extend(archive_audits)
                for side in ("before", "after"):
                    for name, mode in modes[side].items():
                        if mode != modes["native"][name]:
                            known = side == "before" and (modes["native"][name], mode) in {(0o755, 0o777), (0o644, 0o666)}
                            delta.append(dict(side=side, path=name, native=oct(modes["native"][name]),
                                              actual=oct(mode), known_baseline_bug=known))
                append_json(root / "semantic-discrepancies.jsonl", dict(scenario=scenario, sample=sample, mode_differences=delta))
                discrepancies.extend(delta)
                # Keep the known baseline bug visible, but do not accept an unrelated/candidate regression.
                validate_mode_discrepancies(delta, allow_known_baseline=not args.compare_clis)
                for side in SIDES:
                    for binary in ("prototype-app", "prototype-secondary"):
                        executable = f"/bench/{side}/target/dagger/debug/{binary}"
                        output = process(f"{scenario}-{sample}-{side}-{binary}", ["docker", "exec", native_name, executable], side).read_text().strip()
                        app_text = re.search(r'println!\("([^"{}]+): \{\}"', current["application"])[1]
                        lib_text = re.search(r'"(library-[a-z0-9-]+|hello from the library)"', current["library"])[1]
                        expected_output = (app_text if binary == "prototype-app" else "secondary") + ": " + lib_text
                        require(output == expected_output, f"wrong executable behavior: {side}/{binary}: {output!r}")
                print(f"validated {scenario} sample {sample}; modes differ={len(delta)}; "
                      f"archive identifier equivalences={sum(not row['raw_bytes_equal'] for row in archive_audits)}", flush=True)
        verify_cli_hashes(clis, cli_hashes)
        require(all(digest(frozen / name) == value for name, value in module_hashes.items()), "frozen module changed")
        require(digest(ar) == archive_tool["sha256"], "archive reader changed during run")
        if args.compare_clis:
            verify_engine_after()
        summary = {}
        for scenario in EDITS:
            values = {side: {row["sample"]: row["milliseconds"] for row in timings
                            if row["side"] == side and row["scenario"] == scenario and row["sample"] > 0} for side in SIDES}
            saving = [values["before"][i] - values["after"][i] for i in values["before"]]
            summary[scenario] = dict(samples=len(saving), medians={side: statistics.median(list(v.values())) for side, v in values.items()},
                paired_saving_ms=dict(median=statistics.median(saving), mean=statistics.mean(saving), minimum=min(saving), maximum=max(saving)),
                candidate_faster=sum(value > 0 for value in saving),
                paired_native_overhead_ms={side: statistics.median([v - values["native"][i] for i, v in values[side].items()]) for side in ("before", "after")})
        summary["mode_discrepancies"] = len(discrepancies)
        summary["unrecognized_mode_discrepancies"] = sum(not item["known_baseline_bug"] for item in discrepancies)
        summary["archive_comparisons"] = len(archive_comparisons)
        summary["archive_identifier_equivalences"] = sum(not item["raw_bytes_equal"] for item in archive_comparisons)
        summary["all_artifact_raw_bytes_equal"] = all(item["raw_bytes_equal"] for item in archive_comparisons)
        summary["actual_execution_verified"] = False
        summary["scope"] = "Warm invalidation only; OTel actual execution/gates require offline validation. Mode and archive-identifier discrepancies retained, not normalized on disk."
        write_json(root / "summary.json", summary)
        metadata["status"] = "complete-pending-offline-execution-audit"
        print(json.dumps(summary, indent=2), flush=True)
    except BaseException as error:
        metadata.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if args.compare_clis and "before" in metadata["comparison_engine_identity"] and not metadata["comparison_engine_identity"].get("post_attempted"):
            # Failed runs stay failed, but attempt to retain post-run identity
            # without preventing the existing exact-owner native cleanup.
            try:
                verify_engine_after()
            except Exception as error:
                metadata["comparison_engine_identity"]["post_validation_error"] = str(error)
        metadata["finished_unix_ns"] = time.time_ns()
        if native_id and not args.keep_native:
            try:
                inspected = process("cleanup-native-inspect", ["docker", "inspect", native_id])
                identity = json.loads(inspected.read_text())[0]
                verify_native_owner(identity, native_id, nonce)
                process("cleanup-native-remove", ["docker", "rm", "--force", native_id])
                metadata["native_container"]["removed"] = True
            except Exception as error:
                metadata["native_container"]["cleanup_error"] = str(error)
                print(f"Native cleanup not completed: {error}", flush=True)
        write_json(root / "metadata.json", metadata)
        print(f"All workspace/output/evidence retained at {root}; Dagger caches remain under normal engine ownership/GC.", flush=True)


if __name__ == "__main__":
    main()
