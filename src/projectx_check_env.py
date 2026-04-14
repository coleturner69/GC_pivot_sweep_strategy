from __future__ import annotations

import argparse

from .projectx_api import _read_env_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check .projectx.env parsing and credential presence.")
    p.add_argument("--env-file", default=".projectx.env")
    return p


def main() -> None:
    args = build_parser().parse_args()
    values = _read_env_file(args.env_file)

    username = (values.get("PROJECTX_USERNAME") or "").strip()
    api_key = (values.get("PROJECTX_API_KEY") or "").strip()
    token = (values.get("PROJECTX_TOKEN") or "").strip()
    account_id = (values.get("PROJECTX_ACCOUNT_ID") or "").strip()
    contract_id = (values.get("PROJECTX_CONTRACT_ID") or "").strip()

    print(f"env_file={args.env_file}")
    print(f"parsed_keys={','.join(sorted(values.keys())) if values else '<none>'}")
    print(f"username_present={bool(username)}")
    print(f"api_key_present={bool(api_key)}")
    print(f"token_present={bool(token)}")
    print(f"account_id_present={bool(account_id)}")
    print(f"contract_id_present={bool(contract_id)}")

    if username:
        print(f"username_preview={username[:3]}***")
    if api_key:
        print(f"api_key_length={len(api_key)}")
    if token:
        print(f"token_length={len(token)}")


if __name__ == "__main__":
    main()
