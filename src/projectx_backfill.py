from __future__ import annotations

import argparse
from datetime import datetime

import pandas as pd

from .projectx_api import ProjectXClient, ProjectXConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download ProjectX historical bars to CSV.")
    p.add_argument("--contract-id", required=False, help="ProjectX contract ID (optional if auto-resolved)")
    p.add_argument("--start", required=True, help="UTC start time (YYYY-MM-DDTHH:MM:SSZ)")
    p.add_argument("--end", required=True, help="UTC end time (YYYY-MM-DDTHH:MM:SSZ)")
    p.add_argument("--out", default="projectx_gc_1m.csv", help="Output CSV path")
    p.add_argument("--env-file", default=".projectx.env", help="Path to env file with PROJECTX_* values")
    return p


def main() -> None:
    args = build_parser().parse_args()

    client = ProjectXClient(ProjectXConfig.from_env(args.env_file))
    contract_id = client.resolve_contract_id(args.contract_id, symbol_hint="MGC")
    bars = client.retrieve_bars(
        contract_id=contract_id,
        start_time=datetime.fromisoformat(args.start.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(args.end.replace("Z", "+00:00")),
        unit=2,
        unit_number=1,
    )

    if not bars:
        print("No bars returned.")
        return

    df = pd.DataFrame(bars)
    rename_map = {
        "t": "timestamp",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
    }
    for k, v in rename_map.items():
        if k in df.columns:
            df = df.rename(columns={k: v})

    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df.to_csv(args.out, index=False)
    print(f"Saved {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
