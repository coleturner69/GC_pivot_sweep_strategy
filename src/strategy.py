from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

LA_TZ = "America/Los_Angeles"


@dataclass
class Position:
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: float
    level_name: str
    level_price: float


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    level_name: str
    level_price: float
    pnl_points: float


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    ts = pd.to_datetime(df["timestamp"], utc=False)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")

    df = df.copy()
    df["timestamp"] = ts
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="raise")

    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df["timestamp_la"] = df["timestamp"].dt.tz_convert(LA_TZ)

    _validate_one_minute_data(df)
    return df


def _validate_one_minute_data(df: pd.DataFrame) -> None:
    if len(df) < 25:
        raise ValueError("Need at least 25 bars for warm-up and signal checks.")

    diffs = df["timestamp"].diff().dropna()
    if not diffs.empty and (diffs != pd.Timedelta(minutes=1)).any():
        raise ValueError("Input must be continuous 1-minute candles with no gaps.")


def _build_reference_maps(df: pd.DataFrame) -> Tuple[Dict[pd.Timestamp, float], Dict[pd.Timestamp, float]]:
    df = df.copy()
    la = df["timestamp_la"]
    ny_date = la.dt.floor("D")
    ovn_group_date = (la - pd.Timedelta(hours=6, minutes=30)).dt.floor("D")

    t = la.dt.time
    in_ovn = (t >= pd.Timestamp("15:00").time()) | (t <= pd.Timestamp("06:29").time())

    ovn = df.loc[in_ovn].copy()
    ovn["ovn_date"] = ovn_group_date[in_ovn]

    ovn_high = ovn.groupby("ovn_date")["high"].max().to_dict()
    ovn_low = ovn.groupby("ovn_date")["low"].min().to_dict()

    return ovn_high, ovn_low


def run_backtest(df: pd.DataFrame) -> pd.DataFrame:
    ovn_high_map, ovn_low_map = _build_reference_maps(df)

    trades: List[Trade] = []
    position: Optional[Position] = None

    df = df.copy()
    la = df["timestamp_la"]
    local_time = la.dt.time
    session_date = la.dt.floor("D")

    df["vol_avg20"] = df["volume"].rolling(20).mean().shift(1)

    used_level_types: set[Tuple[pd.Timestamp, str]] = set()

    for i in range(20, len(df) - 1):
        bar = df.iloc[i]
        next_bar = df.iloc[i + 1]

        bar_time = bar["timestamp_la"]
        bar_date = session_date.iloc[i]
        t = local_time.iloc[i]

        # Manage open position first.
        if position is not None:
            exit_price, exit_reason = _check_exit(position, bar)
            if exit_reason is None and t >= pd.Timestamp("13:00").time():
                exit_price = float(bar["open"])
                exit_reason = "session_flat"

            if exit_reason is not None:
                pnl = _calc_pnl(position.side, position.entry_price, exit_price)
                trades.append(
                    Trade(
                        side=position.side,
                        entry_time=position.entry_time,
                        entry_price=position.entry_price,
                        exit_time=bar["timestamp"],
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        level_name=position.level_name,
                        level_price=position.level_price,
                        pnl_points=pnl,
                    )
                )
                position = None

            if position is not None:
                continue

        # Entry window: NY session only, and no new entries at/after 12:45 LA.
        if not (pd.Timestamp("06:30").time() <= t <= pd.Timestamp("12:44").time()):
            continue

        vol_avg = bar["vol_avg20"]
        if pd.isna(vol_avg) or vol_avg <= 0:
            continue

        refs = _reference_levels_for_bar(
            df=df,
            idx=i,
            bar_date=bar_date,
            ovn_high_map=ovn_high_map,
            ovn_low_map=ovn_low_map,
            session_date=session_date,
            local_time=local_time,
        )

        for level_name, level_price in refs.items():
            usage_key = (bar_date, level_name)
            if usage_key in used_level_types:
                continue

            signal = _signal_for_level(bar, level_name, level_price)
            if signal is None:
                continue

            if float(bar["volume"]) < 1.5 * float(vol_avg):
                continue

            # Entry at next bar open; protect cutoff.
            next_t = local_time.iloc[i + 1]
            if next_t >= pd.Timestamp("12:45").time():
                continue

            entry_price = float(next_bar["open"])
            side = signal
            stop, target = _stop_target(side, entry_price)
            position = Position(
                side=side,
                entry_time=next_bar["timestamp"],
                entry_price=entry_price,
                stop_price=stop,
                target_price=target,
                level_name=level_name,
                level_price=level_price,
            )
            used_level_types.add(usage_key)
            break

    if position is not None:
        last_bar = df.iloc[-1]
        exit_price = float(last_bar["close"])
        trades.append(
            Trade(
                side=position.side,
                entry_time=position.entry_time,
                entry_price=position.entry_price,
                exit_time=last_bar["timestamp"],
                exit_price=exit_price,
                exit_reason="end_of_data",
                level_name=position.level_name,
                level_price=position.level_price,
                pnl_points=_calc_pnl(position.side, position.entry_price, exit_price),
            )
        )

    out = pd.DataFrame([asdict(t) for t in trades])
    if out.empty:
        return out

    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True)
    out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True)
    return out.sort_values("entry_time").reset_index(drop=True)


def _reference_levels_for_bar(
    df: pd.DataFrame,
    idx: int,
    bar_date: pd.Timestamp,
    ovn_high_map: Dict[pd.Timestamp, float],
    ovn_low_map: Dict[pd.Timestamp, float],
    session_date: pd.Series,
    local_time: pd.Series,
) -> Dict[str, float]:
    refs: Dict[str, float] = {}

    if bar_date in ovn_high_map:
        refs["ovn_high"] = float(ovn_high_map[bar_date])
    if bar_date in ovn_low_map:
        refs["ovn_low"] = float(ovn_low_map[bar_date])

    start = idx
    while start > 0 and session_date.iloc[start - 1] == bar_date:
        start -= 1

    ny_mask = []
    ny_start = pd.Timestamp("06:30").time()
    current_t = local_time.iloc[idx]
    for j in range(start, idx):
        tj = local_time.iloc[j]
        ny_mask.append(ny_start <= tj <= pd.Timestamp("13:00").time() and tj < current_t)

    if any(ny_mask):
        prior_idx = [start + k for k, ok in enumerate(ny_mask) if ok]
        if prior_idx:
            window = df.iloc[prior_idx]
            refs["ny_high"] = float(window["high"].max())
            refs["ny_low"] = float(window["low"].min())

    return refs


def _signal_for_level(bar: pd.Series, level_name: str, level_price: float) -> Optional[str]:
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])

    if level_name.endswith("high"):
        if high >= level_price + 0.2 and close < level_price:
            return "short"
    if level_name.endswith("low"):
        if low <= level_price - 0.2 and close > level_price:
            return "long"
    return None


def _stop_target(side: str, entry_price: float) -> Tuple[float, float]:
    if side == "long":
        return entry_price - 5.0, entry_price + 15.0
    return entry_price + 5.0, entry_price - 15.0


def _check_exit(position: Position, bar: pd.Series) -> Tuple[float, Optional[str]]:
    high = float(bar["high"])
    low = float(bar["low"])

    if position.side == "long":
        stop_hit = low <= position.stop_price
        target_hit = high >= position.target_price
        if stop_hit:
            return position.stop_price, "stop"
        if target_hit:
            return position.target_price, "target"
    else:
        stop_hit = high >= position.stop_price
        target_hit = low <= position.target_price
        if stop_hit:
            return position.stop_price, "stop"
        if target_hit:
            return position.target_price, "target"

    return 0.0, None


def _calc_pnl(side: str, entry: float, exit_price: float) -> float:
    if side == "long":
        return exit_price - entry
    return entry - exit_price
