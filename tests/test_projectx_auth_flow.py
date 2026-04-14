from __future__ import annotations

import unittest

from src.projectx_api import ProjectXApiError, ProjectXClient, ProjectXConfig


class _FakeClient(ProjectXClient):
    def __init__(self) -> None:
        super().__init__(ProjectXConfig(token="seed_token"))
        self.calls: list[str] = []
        self.validated = False

    def _request(self, path, payload, headers):  # type: ignore[override]
        self.calls.append(path)
        if path == "/api/Auth/validate":
            return {"success": True, "newToken": "refreshed_token"}
        if path == "/api/Test/endpoint" and not self.validated:
            self.validated = True
            raise ProjectXApiError("HTTP 401: expired")
        return {"success": True, "value": "ok"}


class TestProjectXAuthFlow(unittest.TestCase):
    def test_post_reauths_once_and_retries_original_path(self) -> None:
        client = _FakeClient()
        result = client._post("/api/Test/endpoint", {"x": 1})

        self.assertEqual(result["value"], "ok")
        self.assertEqual(client._token, "refreshed_token")
        self.assertEqual(
            client.calls,
            ["/api/Test/endpoint", "/api/Auth/validate", "/api/Test/endpoint"],
        )

    def test_validate_session_does_not_recurse_on_401(self) -> None:
        class _Validate401Client(ProjectXClient):
            def __init__(self) -> None:
                super().__init__(ProjectXConfig(token="seed_token"))

            def _request(self, path, payload, headers):  # type: ignore[override]
                raise ProjectXApiError("HTTP 401: expired")

        client = _Validate401Client()
        with self.assertRaises(ProjectXApiError):
            client.validate_session()

    def test_post_reauth_falls_back_to_login_when_validate_401s(self) -> None:
        class _ValidateThenLoginClient(ProjectXClient):
            def __init__(self) -> None:
                super().__init__(ProjectXConfig(username="user", api_key="key", token="seed_token"))
                self.calls: list[str] = []
                self.order_request_count = 0

            def _request(self, path, payload, headers):  # type: ignore[override]
                self.calls.append(path)
                if path == "/api/Test/endpoint":
                    self.order_request_count += 1
                    if self.order_request_count == 1:
                        raise ProjectXApiError("HTTP 401: expired")
                    return {"success": True, "value": "ok"}
                if path == "/api/Auth/validate":
                    raise ProjectXApiError("HTTP 401: expired")
                if path == "/api/Auth/loginKey":
                    return {"success": True, "token": "fresh_login_token"}
                raise AssertionError(f"Unexpected path {path}")

        client = _ValidateThenLoginClient()
        result = client._post("/api/Test/endpoint", {"x": 1})

        self.assertEqual(result["value"], "ok")
        self.assertEqual(client._token, "fresh_login_token")
        self.assertEqual(
            client.calls,
            ["/api/Test/endpoint", "/api/Auth/validate", "/api/Auth/loginKey", "/api/Test/endpoint"],
        )


if __name__ == "__main__":
    unittest.main()
