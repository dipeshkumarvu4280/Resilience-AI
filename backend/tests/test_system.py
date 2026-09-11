import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_root_endpoints(client: AsyncClient):
    # Root info
    res_root = await client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "OPERATIONAL"

    # Root /health
    res_health = await client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"


@pytest.mark.anyio
async def test_system_health(client: AsyncClient):
    response = await client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["phases_active"]["phase_8_field_operations"] is True
    assert data["phases_active"]["phase_9_analytics"] is True


@pytest.mark.anyio
async def test_system_status_services_truthfulness(client: AsyncClient):
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "OPERATIONAL"
    assert data["services"]["platform_core"]["status"] == "Operational"
    assert data["services"]["database_storage"]["status"] == "Operational"
    assert data["services"]["citizen_reporting"]["status"] == "Operational"
    assert data["services"]["gis_mapping"]["status"] == "Operational"
    assert data["services"]["ai_intelligence"]["status"] == "Operational"
    assert data["services"]["field_operations"]["status"] == "Operational"
    assert data["services"]["emergency_analytics"]["status"] == "Operational"
