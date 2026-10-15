#!/usr/bin/env python3
"""Create a workspace with many checks sharing one collection."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
parser.add_argument("--checks", type=int, default=512)
parser.add_argument("--workspace-input", action="store_true", help="Have each check read application.rs")
args = parser.parse_args()
if args.checks < 1:
    parser.error("--checks must be positive")
args.directory.mkdir(parents=True, exist_ok=False)
module = args.directory / "many"
module.mkdir()
(args.directory / "dagger.toml").write_text('[modules.many]\nsource = "./many"\n')
(module / "dagger-module.toml").write_text(
    'name = "many"\nengineVersion = "v1.0.0-0"\n[runtime]\nsource = "dang"\n'
)
signature = "(ws: Workspace!)" if args.workspace_input else ""
body = 'ws.file("application.rs").contents; null' if args.workspace_input else "null"
checks = "\n".join(f"  verify{i}{signature}: Void @check {{ {body} }}" for i in range(args.checks))
if args.workspace_input:
    (args.directory / "application.rs").write_text("const EDIT: u64 = 0;\n")
(module / "main.dang").write_text(
    "type Many {\n  items: Items! { Items() }\n}\n"
    'type Items @collection {\n  names: [String!]! @keys = ["a", "b"]\n'
    "  get(key: String!): Item! { Item(key) }\n}\n"
    "type Item {\n  key: String!\n" + checks + "\n}\n"
)
(args.directory / "keys.graphql").write_text(
    '{ currentWorkspace { artifacts { filterTypes(types: ["Check"]) { '
    'dimensionKeys(dimension: "/many/items") } } } }\n'
)
print(f"Created {args.checks} sibling checks in {args.directory}")
