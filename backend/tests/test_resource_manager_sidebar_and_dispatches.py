import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongodb import get_database
from app.models.enums import UserRole, ResourceType, ResourceStatus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_01_resource_manager_auth_and_me(client: AsyncClient):
    """Test Resource Manager login and /auth/me returns RESOURCE_MANAGER role."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    assert res.status_code == 200, f"Resource Manager login failed: {res.text}"
    token = res.json()["access_token"]
    assert token, "Missing access_token"

    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    user_data = me_res.json()
    assert user_data["role"] == UserRole.RESOURCE_MANAGER.value


@pytest.mark.anyio
async def test_02_resource_manager_field_operations_dispatches(client: AsyncClient):
    """Test Resource Manager has RBAC access to Live Dispatches (field operations tasks)."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    # 1. Overview
    overview_res = await client.get(
        "/api/v1/field-operations/overview",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert overview_res.status_code == 200, f"Overview access failed: {overview_res.text}"

    # 2. Tasks list
    tasks_res = await client.get(
        "/api/v1/field-operations/tasks?limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert tasks_res.status_code == 200, f"Tasks list failed: {tasks_res.text}"
    data = tasks_res.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.anyio
async def test_03_domain_filtering_stockpile(client: AsyncClient):
    """Test domain filtering for Supply Stockpile (Water, Food, Blankets, Clothing)."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_types=Water&resource_types=Food&resource_types=Blankets&resource_types=Clothing&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    allowed = {"Water", "Food", "Blankets", "Clothing"}
    for item in items:
        assert item["resource_type"] in allowed, f"Unexpected resource_type in stockpile: {item['resource_type']}"


@pytest.mark.anyio
async def test_04_domain_filtering_fleet_vehicles(client: AsyncClient):
    """Test domain filtering for Fleet & Vehicles (Transport)."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_type=Transport&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    for item in items:
        assert item["resource_type"] == "Transport", f"Non-transport in fleet view: {item['resource_type']}"


@pytest.mark.anyio
async def test_05_domain_filtering_medical_supplies(client: AsyncClient):
    """Test domain filtering for Medical Supplies."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_types=Medicine&resource_types=First Aid&resource_types=Medical Equipment&resource_types=Healthcare&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    allowed = {"Medicine", "First Aid", "Medical Equipment", "Healthcare"}
    for item in items:
        assert item["resource_type"] in allowed, f"Non-medical in medical view: {item['resource_type']}"


@pytest.mark.anyio
async def test_06_domain_filtering_rations_water(client: AsyncClient):
    """Test domain filtering for Rations & Water."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_types=Water&resource_types=Food&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    allowed = {"Water", "Food"}
    for item in items:
        assert item["resource_type"] in allowed, f"Unexpected item in rations/water: {item['resource_type']}"


@pytest.mark.anyio
async def test_07_domain_filtering_heavy_equipment(client: AsyncClient):
    """Test domain filtering for Heavy Equipment."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_types=Rescue Equipment&resource_types=Protective Equipment&resource_types=Generator&resource_types=Fuel&resource_types=Communication Equipment&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    allowed = {"Rescue Equipment", "Protective Equipment", "Generator", "Fuel", "Communication Equipment"}
    for item in items:
        assert item["resource_type"] in allowed, f"Non-equipment in heavy equipment view: {item['resource_type']}"


@pytest.mark.anyio
async def test_08_domain_filtering_shelters(client: AsyncClient):
    """Test domain filtering for Shelter Capacities."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/resources?resource_type=Shelter&limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    for item in items:
        assert item["resource_type"] == "Shelter", f"Non-shelter in shelters view: {item['resource_type']}"


@pytest.mark.anyio
async def test_09_inventory_dispatch_allocations(client: AsyncClient):
    """Test Inventory Dispatch allocations endpoint."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]

    res = await client.get(
        "/api/v1/needs/allocations?limit=50",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    allocations = res.json()
    assert isinstance(allocations, list)


@pytest.mark.anyio
async def test_10_domain_parameter_filtering_and_stats(client: AsyncClient):
    """Test domain parameter on both list and stats endpoints."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Equipment domain
    eq_res = await client.get("/api/v1/resources?domain=equipment&limit=50", headers=headers)
    assert eq_res.status_code == 200
    eq_stats = await client.get("/api/v1/resources/stats?domain=equipment", headers=headers)
    assert eq_stats.status_code == 200
    assert eq_res.json()["total"] == eq_stats.json()["total_resources"]

    # 2. Rations & Water domain
    rw_res = await client.get("/api/v1/resources?domain=food-water&limit=50", headers=headers)
    assert rw_res.status_code == 200
    rw_stats = await client.get("/api/v1/resources/stats?domain=food-water", headers=headers)
    assert rw_stats.status_code == 200
    assert rw_res.json()["total"] == rw_stats.json()["total_resources"]

    # 3. Medical domain
    med_res = await client.get("/api/v1/resources?domain=medical&limit=50", headers=headers)
    assert med_res.status_code == 200
    med_stats = await client.get("/api/v1/resources/stats?domain=medical", headers=headers)
    assert med_stats.status_code == 200
    assert med_res.json()["total"] == med_stats.json()["total_resources"]


@pytest.mark.anyio
async def test_11_cross_domain_isolation(client: AsyncClient):
    """Verify cross-domain data isolation between Heavy Equipment, Rations & Water, and Medical."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    eq_items = (await client.get("/api/v1/resources?domain=equipment&limit=50", headers=headers)).json()["items"]
    rw_items = (await client.get("/api/v1/resources?domain=food-water&limit=50", headers=headers)).json()["items"]
    med_items = (await client.get("/api/v1/resources?domain=medical&limit=50", headers=headers)).json()["items"]

    eq_ids = {x["resource_id"] for x in eq_items}
    rw_ids = {x["resource_id"] for x in rw_items}
    med_ids = {x["resource_id"] for x in med_items}

    # Intersections must be empty
    assert len(eq_ids.intersection(rw_ids)) == 0, "Heavy Equipment leaked into Rations & Water"
    assert len(eq_ids.intersection(med_ids)) == 0, "Heavy Equipment leaked into Medical Supplies"
    assert len(rw_ids.intersection(med_ids)) == 0, "Rations & Water leaked into Medical Supplies"

