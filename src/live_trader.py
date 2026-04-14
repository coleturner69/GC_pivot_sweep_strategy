from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .projectx_api import ProjectXClient, ProjectXConfig
from .strategy import load_ohlcv_csv, run_backtest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ProjectX live/paper runner for GC pivot sweep strategy.")
    p.add_argument("--contract-id", required=False)
    p.add_argument("--account-id", required=True, type=int)
    p.add_argument("--size", default=1, type=int)
    p.add_argument("--poll-seconds", default=20, type=int)
    p.add_argument("--lookback-minutes", default=1800, type=int)
    p.add_argument("--state-file", default=".live_state.csv")
    p.add_argument("--dry-run", action="store_true", help="Do not place orders, only print signals")
    p.add_argument("--env-file", default=".projectx.env", help="Path to env file with PROJECTX_* values")
    return p


def main() -> None:
    args = build_parser().parse_args()
    client = ProjectXClient(ProjectXConfig.from_env(args.env_file))

    placed_entries = _load_state(Path(args.state_file))

    print("Starting live loop. Press Ctrl+C to stop.")
    while True:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(minutes=args.lookback_minutes)
            contract_id = client.resolve_contract_id(args.contract_id, symbol_hint="MGC")
            bars = client.retrieve_bars(
                contract_id=contract_id,
                start_time=start,
                end_time=end,
                unit=2,
                unit_number=1,
                include_partial_bar=False,
            )

            if not bars:
                time.sleep(args.poll_seconds)
                continue

            df = _bars_to_df(bars)
            tmp_path = Path("/tmp/projectx_live_bars.csv")
            df.to_csv(tmp_path, index=False)
            parsed = load_ohlcv_csv(str(tmp_path))
            trades = run_backtest(parsed)

            if not trades.empty:
                last = trades.iloc[-1]
                entry_ts = pd.Timestamp(last["entry_time"]).isoformat()
                if entry_ts not in placed_entries and pd.Timestamp(last["entry_time"]) >= (end - timedelta(minutes=2)):
                    side = "buy" if last["side"] == "long" else "sell"
                    msg = f"Signal -> {last['side']} @ {last['entry_price']} ({entry_ts})"
                    if args.dry_run:
                        print(f"[DRY RUN] {msg}")
                    else:
                        order_id = client.place_market_order(
                            account_id=args.account_id,
                            contract_id=contract_id,
                            side=side,
                            size=args.size,
                            stop_ticks=50,
                            take_profit_ticks=150,
                            custom_tag="gc_pivot_sweep",
                        )
                        print(f"{msg} | order_id={order_id}")

                    placed_entries.add(entry_ts)
                    _save_state(Path(args.state_file), placed_entries)

        except Exception as exc:  # keep process alive during session
            print(f"Loop error: {exc}")

        time.sleep(args.poll_seconds)


def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    rename_map = {"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    for src, dst in rename_map.items():
        if src in df.columns:
            df = df.rename(columns={src: dst})
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = path.read_text().strip()
    if not data:
        return set()
    return set(x.strip() for x in data.splitlines() if x.strip())


def _save_state(path: Path, placed_entries: set[str]) -> None:
    path.write_text("\n".join(sorted(placed_entries)) + "\n")


if __name__ == "__main__":
    main()
