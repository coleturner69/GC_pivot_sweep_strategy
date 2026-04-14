from __future__ import annotations

import argparse

from .projectx_api import ProjectXClient, ProjectXConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Find ProjectX contracts by symbol/name text.")
    p.add_argument("--query", default="MGC", help="Search text, e.g. MGC")
    p.add_argument("--env-file", default=".projectx.env", help="Path to env file with PROJECTX_* values")
    return p


def main() -> None:
    args = build_parser().parse_args()
    client = ProjectXClient(ProjectXConfig.from_env(args.env_file))

    matches = client.find_contracts(args.query)
    if not matches:
        print("No matching contracts.")
        return

    for c in matches:
        print(
            f"id={c.get('id')} symbol={c.get('symbol')} name={c.get('name')} description={c.get('description')}"
        )


if __name__ == "__main__":
    main()
