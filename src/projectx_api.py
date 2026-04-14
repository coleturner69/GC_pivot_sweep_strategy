from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProjectXApiError(RuntimeError):
    """ProjectX API request/response error."""


@dataclass
class ProjectXConfig:
    username: str = ""
    api_key: str = ""
    token: str = ""
    account_id: Optional[int] = None
    contract_id: Optional[str] = None
    api_base_url: str = "https://api.topstepx.com"
    live: bool = False
    timeout_sec: int = 20
    verbose: bool = False

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "ProjectXConfig":
        file_values = _read_env_file(env_file)

        username = (os.getenv("PROJECTX_USERNAME") or file_values.get("PROJECTX_USERNAME") or "").strip()
        api_key = (os.getenv("PROJECTX_API_KEY") or file_values.get("PROJECTX_API_KEY") or "").strip()
        token = (os.getenv("PROJECTX_TOKEN") or file_values.get("PROJECTX_TOKEN") or "").strip()

        if not token and (not username or not api_key):
            file_note = f" env_file={env_file!r}" if env_file else ""
            found = ",".join(sorted(file_values.keys())) if file_values else "<none>"
            raise ValueError(
                "Missing credentials. Provide PROJECTX_TOKEN or PROJECTX_USERNAME + PROJECTX_API_KEY."
                f"{file_note}; parsed_keys={found}"
            )

        if username.lower() in {"your_username", "username"} or api_key.lower() in {"your_api_key", "api_key"}:
            raise ValueError(
                "Credentials still look like placeholders. Replace PROJECTX_USERNAME/PROJECTX_API_KEY with real values."
            )

        if token.lower() in {"your_token", "token"}:
            raise ValueError("PROJECTX_TOKEN looks like a placeholder; replace with a real token.")

        api_base_url = (
            os.getenv("PROJECTX_API_BASE_URL")
            or file_values.get("PROJECTX_API_BASE_URL")
            or "https://api.topstepx.com"
        )
        live_raw = os.getenv("PROJECTX_LIVE") or file_values.get("PROJECTX_LIVE") or "false"
        timeout_raw = os.getenv("PROJECTX_TIMEOUT_SEC") or file_values.get("PROJECTX_TIMEOUT_SEC") or "20"
        verbose_raw = os.getenv("PROJECTX_DEBUG") or file_values.get("PROJECTX_DEBUG") or "false"

        account_raw = (os.getenv("PROJECTX_ACCOUNT_ID") or file_values.get("PROJECTX_ACCOUNT_ID") or "").strip()
        contract_id = (os.getenv("PROJECTX_CONTRACT_ID") or file_values.get("PROJECTX_CONTRACT_ID") or "").strip()

        return cls(
            username=username,
            api_key=api_key,
            token=token,
            account_id=int(account_raw) if account_raw else None,
            contract_id=contract_id or None,
            api_base_url=api_base_url.rstrip("/"),
            live=str(live_raw).lower() == "true",
            timeout_sec=int(timeout_raw),
            verbose=str(verbose_raw).lower() == "true",
        )


class ProjectXClient:
    def __init__(self, config: ProjectXConfig):
        self.config = config
        self._token: Optional[str] = config.token or None
        self._is_validating_session = False

    def authenticate(self) -> str:
        if self._token:
            return self._token

        if not self.config.username or not self.config.api_key:
            raise ProjectXApiError(
                "Cannot authenticate via /api/Auth/loginKey without PROJECTX_USERNAME and PROJECTX_API_KEY."
            )

        payload = {"userName": self.config.username, "apiKey": self.config.api_key}
        data = self._post("/api/Auth/loginKey", payload, include_auth=False)
        token = data.get("token")
        if not token:
            raise ProjectXApiError("Authentication succeeded but token was missing.")
        self._token = token
        return token

    def validate_session(self) -> str:
        if not self._token:
            raise ProjectXApiError("Cannot validate session without an existing token.")

        self._is_validating_session = True
        headers = {
            "accept": "text/plain",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        try:
            data = self._request(path="/api/Auth/validate", payload={}, headers=headers)
            if not data.get("success", False):
                raise ProjectXApiError(f"API error {data.get('errorCode')}: {data.get('errorMessage')}")
            new_token = data.get("newToken")
            if not new_token:
                raise ProjectXApiError("Validate session succeeded but newToken was missing.")
            self._token = new_token
            return new_token
        finally:
            self._is_validating_session = False

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
            "limitPrice": None,
            "stopPrice": None,
            "trailPrice": None,
            "customTag": None,
        }
        if custom_tag:
            payload["customTag"] = custom_tag
        if stop_ticks is not None:
            payload["stopLossBracket"] = {"ticks": int(stop_ticks), "type": 1}
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

        if self.config.contract_id:
            return self.config.contract_id

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

    def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        include_auth: bool = True,
        allow_reauth: bool = True,
    ) -> Dict[str, Any]:
        if include_auth and not self._token:
            self.authenticate()

        headers = {"accept": "text/plain", "Content-Type": "application/json"}
        if include_auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            data = self._request(path=path, payload=payload, headers=headers)
        except ProjectXApiError as exc:
            should_reauth = include_auth and allow_reauth and path != "/api/Auth/validate" and "HTTP 401" in str(exc)
            if should_reauth:
                self._refresh_session_after_401(original_exc=exc)
                headers["Authorization"] = f"Bearer {self._token}"
                data = self._request(path=path, payload=payload, headers=headers)
            else:
                raise

        if not data.get("success", False):
            error_message = data.get("errorMessage") or "No errorMessage returned by API."
            raise ProjectXApiError(f"API error {data.get('errorCode')}: {error_message}")
        return data

    def _refresh_session_after_401(self, original_exc: Optional[ProjectXApiError] = None) -> None:
        if self._is_validating_session:
            raise ProjectXApiError("Session refresh loop detected while validating token.")

        if self._token:
            try:
                self.validate_session()
                return
            except ProjectXApiError as exc:
                if "HTTP 401" not in str(exc):
                    raise
                if not self.config.username or not self.config.api_key:
                    raise ProjectXApiError(
                        "Token rejected with HTTP 401 and no loginKey credentials configured. "
                        "Set PROJECTX_USERNAME + PROJECTX_API_KEY or provide a fresh PROJECTX_TOKEN."
                    ) from exc

        self._token = None
        self.authenticate()

    def _request(self, path: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.config.api_base_url.rstrip('/')}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(url=url, data=body, headers=headers, method="POST")

        if self.config.verbose:
            print(f"[ProjectX] POST {url}")

        try:
            with urlopen(request, timeout=self.config.timeout_sec) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as exc:
            msg = exc.read().decode("utf-8", errors="replace")
            raise ProjectXApiError(f"HTTP {exc.code}: {msg}") from exc
        except URLError as exc:
            raise ProjectXApiError(f"Network error: {exc}") from exc


def _read_env_file(env_file: Optional[str]) -> Dict[str, str]:
    if not env_file:
        return {}

    path = Path(env_file).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        k, v = line.split("=", 1)
        key = k.strip()
        value = v.strip()

        if not key:
            continue

        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        value = value.strip("\"'")
        values[key] = value

    return values
def _to_utc_iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return ts.isoformat().replace("+00:00", "Z")
