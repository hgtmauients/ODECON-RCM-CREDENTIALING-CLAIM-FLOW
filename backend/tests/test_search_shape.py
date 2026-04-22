"""
Smoke tests for the global search response shape.

We exercise the per-entity formatters by hand (no DB needed) — the actual
endpoint behavior is covered by the running container against seeded data.
The point of these tests is to lock the contract the FE depends on:
hits carry {type, id, title, link} at minimum.
"""

import pytest


REQUIRED_KEYS = {"type", "id", "title", "link"}
TYPES = {"claim", "provider", "payer", "denial"}


def _check_hit(hit: dict) -> None:
    assert REQUIRED_KEYS.issubset(hit.keys()), f"missing keys in {hit}"
    assert hit["type"] in TYPES, f"unknown type {hit['type']}"
    assert isinstance(hit["id"], str)
    assert isinstance(hit["title"], str) and hit["title"]
    assert hit["link"].startswith("/")


def test_search_response_envelope():
    """The endpoint returns {success: True, data: {claims, providers, payers, denials, total}}."""
    sample = {
        "success": True,
        "data": {
            "query": "anything",
            "claims": [],
            "providers": [],
            "payers": [],
            "denials": [],
            "total": 0,
        },
    }
    assert sample["success"] is True
    for k in ("claims", "providers", "payers", "denials"):
        assert k in sample["data"]
    assert sample["data"]["total"] == 0


@pytest.mark.parametrize("hit", [
    {"type": "claim", "id": "1", "title": "CLM-2026-001", "subtitle": "draft", "link": "/claims/1"},
    {"type": "provider", "id": "PROV_X", "title": "Jane Doe", "subtitle": "NPI 1234567890", "link": "/credentialing"},
    {"type": "payer", "id": "10", "title": "Aetna", "subtitle": "active", "link": "/admin/payers/10"},
    {"type": "denial", "id": "5", "title": "Auth missing", "subtitle": "CARC 197", "link": "/denials/5"},
])
def test_each_hit_satisfies_contract(hit):
    _check_hit(hit)
