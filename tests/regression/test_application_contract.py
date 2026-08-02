"""Characterization guardrail for routes and unauthenticated public responses."""

from __future__ import annotations

import hashlib
import sys

import app as app_module


EXPECTED_ROUTE_COUNT = 59
EXPECTED_ROUTE_SHA256 = "5f20377dc6d2715b3929a4fcd08e2a5eec6d47c7dbd883a2ef595104e029b7ad"


def _route_payload() -> str:
    routes = sorted(
        (
            rule.endpoint,
            tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})),
            rule.rule,
        )
        for rule in app_module.app.url_map.iter_rules()
    )
    return "\n".join(
        endpoint + "|" + ",".join(methods) + "|" + rule
        for endpoint, methods, rule in routes
    )


def test_route_manifest_is_unchanged() -> None:
    payload = _route_payload()
    assert len(payload.splitlines()) == EXPECTED_ROUTE_COUNT
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == EXPECTED_ROUTE_SHA256


def test_public_and_guarded_route_smoke_contract() -> None:
    client = app_module.app.test_client()
    expected = {
        "/landing": (200, None, "text/html"),
        "/login": (200, None, "text/html"),
        "/new": (200, None, "text/html"),
        "/guide": (200, None, "text/html"),
        "/": (200, None, "text/html"),
        "/explore": (302, "/login", "text/html"),
        "/visualize": (302, "/login", "text/html"),
        "/static/favicon.svg": (200, None, "image/svg+xml"),
        "/does-not-exist": (404, None, "text/html"),
    }

    for path, (status, location, mimetype) in expected.items():
        response = client.get(path)
        assert response.status_code == status, path
        assert response.headers.get("Location") == location, path
        assert response.mimetype == mimetype, path


def main() -> int:
    checks = [
        ("route manifest", test_route_manifest_is_unchanged),
        ("public/guarded route smoke contract", test_public_and_guarded_route_smoke_contract),
    ]
    failures = 0
    for name, check in checks:
        try:
            check()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL  {name}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
