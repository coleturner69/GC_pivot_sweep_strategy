from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class ProjectXApiError(RuntimeError):
    """ProjectX API request/response error."""


@dataclass
class ProjectXConfig:
    username: str
    api_key: str
    api_base_url: str = "https://api.thefuturesdesk.projectx.com"
    live: bool = False
    timeout_sec: int = 20

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "ProjectXConfig":
        file_values = _read_env_file(env_file)

        username = os.getenv("PROJECTX_USERNAME") or file_values.get("PROJECTX_USERNAME")
        api_key = os.getenv("PROJECTX_API_KEY") or file_values.get("PROJECTX_API_KEY")
        if not username or not api_key:
            raise ValueError(
                "Missing credentials. Set PROJECTX_USERNAME and PROJECTX_API_KEY in env vars or an env file."
            )

        api_base_url = (
            os.getenv("PROJECTX_API_BASE_URL")
            or file_values.get("PROJECTX_API_BASE_URL")
            or "https://api.thefuturesdesk.projectx.com"
        )
        live_raw = os.getenv("PROJECTX_LIVE") or file_values.get("PROJECTX_LIVE") or "false"

        return cls(
            username=username,
            api_key=api_key,
            api_base_url=api_base_url,
            live=str(live_raw).lower() == "true",
        )


class ProjectXClient:
    def __init__(self, config: ProjectXConfig):
        self.config = config
        self._session = requests.Session()
        self._token: Optional[str] = None

    def authenticate(self) -> str:
        payload = {"userName": self.config.username, "apiKey": self.config.api_key}
        data = self._post("/api/Auth/loginKey", payload, include_auth=False)
        token = data.get("token")
        if not token:
            raise ProjectXApiError("Authentication succeeded but token was missing.")
        self._token = token
        return token

    def validate_session(self) -> str:
        data = self._post("/api/Auth/validate", {})
        new_token = data.get("newToken")
        if not new_token:
            raise ProjectXApiError("Validate session succeeded but newToken was missing.")
        self._token = new_token
        return new_token

    def search_accounts(self, only_active_accounts: bool = True) -> List[Dict[str, Any]]:
        data = self._post("/api/Account/search", {"onlyActiveAccounts": only_active_accounts})
        return data.get("accounts", [])

    def list_available_contracts(self, live: Optional[bool] = None) -> List[Dict[str, Any]]:
        data = self._post("/api/Contract/available", {"live": self.config.live if live is None else live})
        return data.get("contracts", [])

    def retrieve_bars(
        self,
        contract_id: str,
        start_time: datetime,
        end_time: datetime,
        unit: int = 2,
        unit_number: int = 1,
        limit: int = 20_000,
        include_partial_bar: bool = False,
    ) -> List[Dict[str, Any]]:
        payload = {
            "contractId": contract_id,
            "live": self.config.live,
            "startTime": _to_utc_iso(start_time),
            "endTime": _to_utc_iso(end_time),
            "unit": unit,
            "unitNumber": unit_number,
            "limit": limit,
            "includePartialBar": include_partial_bar,
        }
        data = self._post("/api/History/retrieveBars", payload)
        return data.get("bars", [])

    def place_market_order(
        self,
        account_id: int,
        contract_id: str,
        side: str,
        size: int,
        stop_ticks: Optional[int] = None,
        take_profit_ticks: Optional[int] = None,
        custom_tag: Optional[str] = None,
    ) -> int:
        side_int = 0 if side.lower() == "buy" else 1

        payload: Dict[str, Any] = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": 2,
            "side": side_int,
            "size": size,
        }
        if custom_tag:
            payload["customTag"] = custom_tag
        if stop_ticks is not None:
            payload["stopLossBracket"] = {"ticks": int(stop_ticks), "type": 4}
        if take_profit_ticks is not None:
            payload["takeProfitBracket"] = {"ticks": int(take_profit_ticks), "type": 1}

        data = self._post("/api/Order/place", payload)
        order_id = data.get("orderId")
        if order_id is None:
            raise ProjectXApiError("Order placed but orderId missing.")
        return int(order_id)


    def find_contracts(self, symbol_contains: str, live: Optional[bool] = None) -> List[Dict[str, Any]]:
        symbol_contains = symbol_contains.lower().strip()
        contracts = self.list_available_contracts(live=live)
        out: List[Dict[str, Any]] = []
        for c in contracts:
            text = " ".join(str(c.get(k, "")) for k in ("symbol", "name", "description", "id")).lower()
            if symbol_contains in text:
                out.append(c)
        return out

    def resolve_contract_id(self, contract_id: Optional[str] = None, symbol_hint: str = "MGC") -> str:
        if contract_id:
            return str(contract_id)

        env_id = os.getenv("PROJECTX_MICRO_GOLD_CONTRACT_ID")
        if env_id:
            return env_id

        matches = self.find_contracts(symbol_hint)
        if not matches:
            raise ProjectXApiError(
                f"No contracts matched symbol hint '{symbol_hint}'. Set PROJECTX_MICRO_GOLD_CONTRACT_ID explicitly."
            )
        if len(matches) > 1:
            ids = [str(m.get("id")) for m in matches[:10]]
            raise ProjectXApiError(
                f"Multiple contracts matched '{symbol_hint}' (sample ids: {ids}). Set PROJECTX_MICRO_GOLD_CONTRACT_ID explicitly."
            )

        selected_id = matches[0].get("id")
        if selected_id is None:
            raise ProjectXApiError("Matched contract is missing id field.")
        return str(selected_id)

    def _post(self, path: str, payload: Dict[str, Any], include_auth: bool = True) -> Dict[str, Any]:
        if include_auth and not self._token:
            self.authenticate()

        url = f"{self.config.api_base_url}{path}"
        headers = {"accept": "text/plain", "Content-Type": "application/json"}
        if include_auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = self._session.post(url, json=payload, headers=headers, timeout=self.config.timeout_sec)
        if response.status_code == 401 and include_auth:
            self.validate_session()
            headers["Authorization"] = f"Bearer {self._token}"
            response = self._session.post(url, json=payload, headers=headers, timeout=self.config.timeout_sec)

        if response.status_code >= 400:
            raise ProjectXApiError(f"HTTP {response.status_code}: {response.text}")

        data = response.json()
        if not data.get("success", False):
            raise ProjectXApiError(
                f"API error {data.get('errorCode')}: {data.get('errorMessage')}"
            )
        return data


def _read_env_file(env_file: Optional[str]) -> Dict[str, str]:
    if not env_file:
        return {}

    path = Path(env_file)
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip("\"'")
    return values


def _to_utc_iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return ts.isoformat().replace("+00:00", "Z")
