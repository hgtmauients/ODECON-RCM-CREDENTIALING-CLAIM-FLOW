"""
Smoke tests for the role-check coverage closed in v11.

Each test exercises Principal.require_role() directly against a representative
set of routes that previously had no role enforcement (NEW-C4).
"""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from api.auth import Principal


def _readonly_principal() -> Principal:
    return Principal(
        user_id="u1", tenant_id="t1", email="ro@example.com", roles=["readonly"],
    )


def _billing_principal() -> Principal:
    return Principal(
        user_id="u1", tenant_id="t1", email="b@example.com", roles=["billing"],
    )


def _admin_principal() -> Principal:
    return Principal(
        user_id="u1", tenant_id="t1", email="a@example.com", roles=["admin"],
    )


def _credentialing_principal() -> Principal:
    return Principal(
        user_id="u1", tenant_id="t1", email="c@example.com", roles=["credentialing"],
    )


def test_readonly_cannot_act_as_billing():
    with pytest.raises(HTTPException) as ei:
        _readonly_principal().require_role("billing")
    assert ei.value.status_code == 403


def test_readonly_cannot_act_as_credentialing():
    with pytest.raises(HTTPException) as ei:
        _readonly_principal().require_role("credentialing")
    assert ei.value.status_code == 403


def test_billing_cannot_act_as_admin():
    with pytest.raises(HTTPException):
        _billing_principal().require_role("admin")


def test_billing_cannot_act_as_credentialing():
    with pytest.raises(HTTPException):
        _billing_principal().require_role("credentialing")


def test_admin_can_act_as_billing_and_credentialing_and_admin():
    p = _admin_principal()
    p.require_role("billing")
    p.require_role("credentialing")
    p.require_role("admin")


def test_credentialing_cannot_act_as_billing_or_admin():
    p = _credentialing_principal()
    with pytest.raises(HTTPException):
        p.require_role("billing")
    with pytest.raises(HTTPException):
        p.require_role("admin")
    p.require_role("credentialing")  # self


@pytest.mark.asyncio
async def test_readonly_blocked_from_global_search_endpoint():
    from api.search import global_search

    with pytest.raises(HTTPException) as ei:
        await global_search(q="abc", db=AsyncMock(), current_user=_readonly_principal())
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_readonly_blocked_from_dashboard_summary_endpoint():
    from api.dashboard import dashboard_summary

    with pytest.raises(HTTPException) as ei:
        await dashboard_summary(db=AsyncMock(), current_user=_readonly_principal())
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_billing_blocked_from_caqh_admin_endpoint():
    from api.rcm.caqh import search_caqh_by_npi

    with pytest.raises(HTTPException) as ei:
        await search_caqh_by_npi(npi="1234567890", db=AsyncMock(), current_user=_billing_principal())
    assert ei.value.status_code == 403
