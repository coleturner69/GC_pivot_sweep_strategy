from __future__ import annotations

import argparse

from .strategy import load_ohlcv_csv, run_backtest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backtest GC pivot-sweep strategy on 1-minute CSV data.")
    p.add_argument("csv_path", help="Path to OHLCV CSV")
    p.add_argument("--out", default="trades.csv", help="Path for trade output CSV")
    return p


def main() -> None:
    args = build_parser().parse_args()

    df = load_ohlcv_csv(args.csv_path)
    trades = run_backtest(df)
    trades.to_csv(args.out, index=False)

    if trades.empty:
        print("No trades generated.")
        return

    wins = (trades["pnl_points"] > 0).sum()
    total = len(trades)
    print(f"Trades: {total}")
    print(f"Win rate: {wins / total:.2%}")
    print(f"Net points: {trades['pnl_points'].sum():.2f}")
    print(f"Avg points/trade: {trades['pnl_points'].mean():.2f}")
    print(f"Saved trades -> {args.out}")


if __name__ == "__main__":
    main()
