#!/usr/bin/env python3
"""Create a workspace that discovers one collection's keys through many checks."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
parser.add_argument("--checks", type=int, default=512)
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
checks = "\n".join(f"  verify{i}: Void @check {{ null }}" for i in range(args.checks))
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
