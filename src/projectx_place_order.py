from __future__ import annotations

import argparse

from .projectx_api import ProjectXClient, ProjectXConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Place a ProjectX market order (for paper/live testing).")
    p.add_argument("--env-file", default=".projectx.env")
    p.add_argument("--account-id", type=int, help="Overrides PROJECTX_ACCOUNT_ID")
    p.add_argument("--contract-id", help="Overrides PROJECTX_CONTRACT_ID")
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--size", type=int, default=1)
    p.add_argument("--stop-ticks", type=int)
    p.add_argument("--take-profit-ticks", type=int)
    p.add_argument("--tag", default="gc_pivot_sweep_manual")
    return p


def main() -> None:
    args = build_parser().parse_args()
    config = ProjectXConfig.from_env(args.env_file)
    client = ProjectXClient(config)

    account_id = args.account_id or config.account_id
    if account_id is None:
        raise ValueError("Provide --account-id or set PROJECTX_ACCOUNT_ID in env file.")

    contract_id = args.contract_id or config.contract_id
    if not contract_id:
        contract_id = client.resolve_contract_id(None, symbol_hint="MGC")

    order_id = client.place_market_order(
        account_id=account_id,
        contract_id=contract_id,
        side=args.side,
        size=args.size,
        stop_ticks=args.stop_ticks,
        take_profit_ticks=args.take_profit_ticks,
        custom_tag=args.tag,
    )
    print(f"Placed order_id={order_id} account_id={account_id} contract_id={contract_id}")


if __name__ == "__main__":
    main()
