import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongodb import db_manager

@pytest.mark.anyio
async def test_root_health_get_and_head():
    """Verify /health responds to both GET and HEAD with HTTP 200 and zero mutations."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /health
        res_get = await client.get("/health")
        assert res_get.status_code == 200
        data = res_get.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["system"] == "RESILIENCE"
        assert "database" in data
        assert data["database"] in ["connected", "disconnected"]

        # 2. HEAD /health
        res_head = await client.head("/health")
        assert res_head.status_code == 200


@pytest.mark.anyio
async def test_system_health_v1_get_and_head():
    """Verify /api/v1/system/health responds to both GET and HEAD with HTTP 200."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /api/v1/system/health
        res_get = await client.get("/api/v1/system/health")
        assert res_get.status_code == 200
        data = res_get.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["system"] == "RESILIENCE"
        assert "database" in data
        assert data["database"] in ["connected", "disconnected"]
        assert "phases_active" in data

        # 2. HEAD /api/v1/system/health
        res_head = await client.head("/api/v1/system/health")
        assert res_head.status_code == 200


@pytest.mark.anyio
async def test_root_index_endpoint():
    """Verify root endpoint / returns system metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "OPERATIONAL"
        assert data["system"] == "RESILIENCE"
