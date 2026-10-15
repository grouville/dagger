#!/usr/bin/env python3
"""Generate a Rust workspace with many leaves sharing one dependency."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--leaves", type=int, default=1024)
    parser.add_argument("--root-package", action="store_true")
    parser.add_argument("--module", required=True)
    parser.add_argument("--cache-key", required=True)
    args = parser.parse_args()
    if args.leaves < 1:
        parser.error("--leaves must be positive")
    args.root.mkdir(parents=True, exist_ok=False)

    names = [f"leaf_{i:04d}" for i in range(args.leaves)]
    members = ["shared", *names, "app"]
    workspace_members = members[:-1] if args.root_package else members
    (args.root / "Cargo.toml").write_text(
        "[workspace]\nmembers = " + json.dumps(workspace_members)
        + '\nresolver = "2"\n\n[profile.dev]\ncodegen-units = 16\n'
    )
    for name in members:
        root_package = name == "app" and args.root_package
        package = args.root if root_package else args.root / name
        (package / "src").mkdir(parents=True)
        prefix = "" if root_package else "../"
        dependencies = ""
        if name != "shared":
            dependencies = f'shared = {{ path = "{prefix}shared" }}\n'
        if name == "app":
            dependencies += "".join(
                f'{leaf} = {{ path = "{prefix}{leaf}" }}\n' for leaf in names
            )
        manifest = (
            f'[package]\nname = "{name}"\nversion = "0.1.0"\n'
            'edition = "2021"\n\n[dependencies]\n' + dependencies
        )
        with (package / "Cargo.toml").open("a" if root_package else "w") as file:
            file.write("\n" + manifest if root_package else manifest)
        if name == "app":
            statements = "".join(
                f"    value = value.wrapping_add({leaf}::value());\n"
                for leaf in names
            )
            (package / "src/main.rs").write_text(
                "fn main() {\n    let mut value = 0u64;\n" + statements
                + '    println!("{}", value);\n}\n'
            )
        else:
            expression = "EDIT" if name == "shared" else "shared::value().wrapping_add(EDIT)"
            (package / "src/lib.rs").write_text(
                f"pub const EDIT: u64 = 0;\npub fn value() -> u64 {{ {expression} }}\n"
            )
    (args.root / "dagger.toml").write_text(
        "[modules.rust]\nsource = " + json.dumps(args.module)
        + '\n[modules.rust.settings]\nimage = '
        + json.dumps("rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42")
        + "\nlocked = true\nnativeCache = true\ncacheKey = "
        + json.dumps(args.cache_key) + "\n"
    )


if __name__ == "__main__":
    main()
