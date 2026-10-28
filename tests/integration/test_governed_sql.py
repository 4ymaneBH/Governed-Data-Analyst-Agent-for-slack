"""Exercise the REST tool boundary against live OPA and PostgreSQL services."""

import os
import uuid

import httpx
import pytest
import pytest_asyncio

from services.mcp_server import server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="requires live PostgreSQL and OPA services",
    ),
]


@pytest_asyncio.fixture
async def client():
    async with server.lifespan(server.app):
        pool = await server.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reporting.daily_kpis (date, region, revenue) "
                "VALUES (DATE '2026-01-01', 'NA', 100.00)"
            )

        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client


@pytest.mark.asyncio
async def test_allowed_query_returns_data_and_audit(client):
    request_id = uuid.uuid4()
    response = await client.post(
        "/api/run_sql",
        params={
            "query": "SELECT region FROM reporting.daily_kpis ORDER BY id LIMIT 1",
            "user_id": "marketing-user",
            "slack_user_id": "U_MARKETING",
            "role": "marketing",
            "request_id": str(request_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == [{"region": "NA"}]

    pool = await server.get_db_pool()
    async with pool.acquire() as conn:
        decision = await conn.fetchval(
            "SELECT policy_decision FROM internal.audit_logs WHERE request_id = $1",
            request_id,
        )
    assert decision == "ALLOW"


@pytest.mark.asyncio
async def test_intern_query_is_denied_and_audited(client):
    request_id = uuid.uuid4()
    response = await client.post(
        "/api/run_sql",
        params={
            "query": "SELECT region FROM reporting.daily_kpis LIMIT 1",
            "user_id": "intern-user",
            "slack_user_id": "U_INTERN",
            "role": "intern",
            "request_id": str(request_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"].startswith("Access denied:")

    pool = await server.get_db_pool()
    async with pool.acquire() as conn:
        decision = await conn.fetchval(
            "SELECT policy_decision FROM internal.audit_logs WHERE request_id = $1",
            request_id,
        )
    assert decision == "DENY"
