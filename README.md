# GC Pivot Sweep Strategy (v1)

This repository implements your 1-minute Gold futures sweep/reclaim strategy and includes ProjectX / TopstepX integration for historical and live/paper workflows.

## If you do NOT have a local shell

Use an **env file** instead of shell exports.
Create a file named `.projectx.env` in the repo root:

```env
# Option A: token-based auth
PROJECTX_TOKEN=your_token

# Option B: username/api-key auth
PROJECTX_USERNAME=your_username
PROJECTX_API_KEY=your_api_key

# Common settings
PROJECTX_LIVE=false
PROJECTX_API_BASE_URL=https://api.topstepx.com
PROJECTX_ACCOUNT_ID=12345
PROJECTX_CONTRACT_ID=CON.F.US.MGC.M26
```

All ProjectX CLIs now accept `--env-file` (default `.projectx.env`).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Credential troubleshooting

If account lookup says credentials are missing, run:

```bash
python -m src.projectx_check_env --env-file .projectx.env
```

## Place a single test market order (paper first)

```bash
python -m src.projectx_place_order \
  --side sell \
  --size 1 \
  --env-file .projectx.env
```

Optional bracket example:

```bash
python -m src.projectx_place_order \
  --side sell \
  --size 1 \
  --stop-ticks 50 \
  --take-profit-ticks 150 \
  --env-file .projectx.env
```

## Get your Account ID

```bash
python -m src.projectx_find_account --env-file .projectx.env
```

The output prints account IDs you can pass into `--account-id`.

## Contract discovery (Micro Gold)

```bash
python -m src.projectx_find_contract --query MGC --env-file .projectx.env
```

If a single clear contract is returned, you can use it directly. If multiple are returned, copy the correct id into `.projectx.env` as `PROJECTX_CONTRACT_ID=...`.

## Pull historical 1-minute data from ProjectX

```bash
python -m src.projectx_backfill \
  --start 2026-01-01T00:00:00Z \
  --end 2026-01-31T23:59:00Z \
  --out mgc_jan_2026_1m.csv \
  --env-file .projectx.env
```

## Backtest from CSV

```bash
python -m src.backtest mgc_jan_2026_1m.csv --out trades.csv
```

## Paper/live loop (1 micro contract)

```bash
python -m src.live_trader \
  --size 1 \
  --dry-run \
  --env-file .projectx.env
```

Remove `--dry-run` only after validating behavior in paper mode.
