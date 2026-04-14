from __future__ import annotations

import argparse

from .projectx_api import ProjectXClient, ProjectXConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="List ProjectX accounts and IDs.")
    p.add_argument("--env-file", default=".projectx.env", help="Path to env file with PROJECTX_* values")
    p.add_argument("--all", action="store_true", help="Include inactive accounts")
    return p


def main() -> None:
    args = build_parser().parse_args()
    client = ProjectXClient(ProjectXConfig.from_env(args.env_file))

    accounts = client.search_accounts(only_active_accounts=not args.all)
    if not accounts:
        print("No accounts returned.")
        return

    for a in accounts:
        print(
            "id={id} name={name} active={active} balance={balance}".format(
                id=a.get("id"),
                name=a.get("name") or a.get("accountName"),
                active=a.get("active") or a.get("isActive"),
                balance=a.get("balance") or a.get("cashBalance"),
            )
        )


if __name__ == "__main__":
    main()
