import pytest
from httpx import AsyncClient
from app.core.security import create_access_token


@pytest.mark.anyio
async def test_admin_platform_config_crud_and_rbac(client: AsyncClient, db):
    # 1. Non-admin cannot access platform config
    volunteer_token = create_access_token(
        data={"sub": "9999999002", "email": "officer.vance@resilience.gov", "role": "EMERGENCY_OFFICER"}
    )
    res = await client.get(
        "/api/v1/system/config",
        headers={"Authorization": f"Bearer {volunteer_token}"},
    )
    assert res.status_code == 403

    # 2. Admin can get platform config
    admin_token = create_access_token(
        data={"sub": "9999999001", "email": "commander.jenkins@resilience.gov", "role": "ADMIN"}
    )
    res = await client.get(
        "/api/v1/system/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    config_data = res.json()
    assert "spatial_cluster_radius_km" in config_data
    assert "require_human_approval_for_dispatch" in config_data

    # 3. Admin can update platform config
    update_payload = {
        "spatial_cluster_radius_km": 6.5,
        "temporal_window_hours": 3,
        "require_human_approval_for_dispatch": True,
        "audit_retention_days": 180,
    }
    res = await client.put(
        "/api/v1/system/config",
        json=update_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["spatial_cluster_radius_km"] == 6.5
    assert updated["temporal_window_hours"] == 3
    assert updated["audit_retention_days"] == 180


@pytest.mark.anyio
async def test_admin_merged_audit_logs(client: AsyncClient, db):
    admin_token = create_access_token(
        data={"sub": "9999999001", "email": "commander.jenkins@resilience.gov", "role": "ADMIN"}
    )
    res = await client.get(
        "/api/v1/users/audit-logs?limit=20",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)

    # Non-admin cannot access admin audit logs
    officer_token = create_access_token(
        data={"sub": "9999999002", "email": "officer.vance@resilience.gov", "role": "EMERGENCY_OFFICER"}
    )
    res = await client.get(
        "/api/v1/users/audit-logs",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 403


@pytest.mark.anyio
async def test_volunteer_profile_update_and_persistence(client: AsyncClient, db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Create test volunteer in database
    await db.users.update_one(
        {"email": "volunteer_tester@resilience.test"},
        {
            "$set": {
                "id": "vol-tester-101",
                "email": "volunteer_tester@resilience.test",
                "full_name": "Volunteer Tester",
                "phone": "+1555123456",
                "role": "VOLUNTEER",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "volunteer_profile": {
                    "skills": ["Community First Response"],
                    "availability": "Available Immediately",
                    "zone_or_district": "Metro Sector 01",
                },
            }
        },
        upsert=True,
    )

    volunteer_token = create_access_token(
        data={"sub": "+1555123456", "email": "volunteer_tester@resilience.test", "role": "VOLUNTEER"}
    )

    # Update volunteer skills & availability
    payload = {
        "full_name": "Volunteer Tester Updated",
        "phone": "+1555987654",
        "volunteer_profile": {
            "skills": ["Emergency First Aid & CPR", "Disaster Shelter Support", "Flood & Water Rescue"],
            "availability": "Standby (Within 2 Hours)",
            "zone_or_district": "Metro Sector 02",
            "address": "45 Waterfront Blvd",
        },
    }

    res = await client.patch(
        "/api/v1/users/me/profile",
        json=payload,
        headers={"Authorization": f"Bearer {volunteer_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "Volunteer Tester Updated"
    assert data["phone"] == "+1555987654"
    assert "Flood & Water Rescue" in data["volunteer_profile"]["skills"]
    assert data["volunteer_profile"]["availability"] == "Standby (Within 2 Hours)"
    assert data["volunteer_profile"]["zone_or_district"] == "Metro Sector 02"

    # Verify DB persistence
    db_user = await db.users.find_one({"email": "volunteer_tester@resilience.test"})
    assert db_user is not None
    assert db_user["full_name"] == "Volunteer Tester Updated"
    assert db_user["volunteer_profile"]["availability"] == "Standby (Within 2 Hours)"


@pytest.mark.anyio
async def test_resource_domain_filtering_and_stats(client: AsyncClient, db):
    """Verify backend supports distinct domain-specific resource queries and stats without mixing assets."""
    rm_token = create_access_token(
        data={"sub": "9999999003", "email": "elena.rostova@resilience.gov", "role": "RESOURCE_MANAGER"}
    )
    rm_headers = {"Authorization": f"Bearer {rm_token}"}

    # Insert test resources of diverse types
    await db.resources.delete_many({"owner": "DomainFilterTester"})
    test_docs = [
        {
            "resource_id": "RES-TEST-VEH-01",
            "name": "Rapid Evacuation Ambulance 01",
            "resource_type": "Transport",
            "category": "Emergency Medical Transport",
            "quantity_total": 5.0,
            "quantity_available": 5.0,
            "unit": "Vehicles",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "owner": "DomainFilterTester",
            "location": {"address": "District Ambulance Station", "latitude": 28.6139, "longitude": 77.2090},
        },
        {
            "resource_id": "RES-TEST-MED-01",
            "name": "Trauma Care Kit A",
            "resource_type": "Medicine",
            "category": "First Aid & Pharmaceuticals",
            "quantity_total": 100.0,
            "quantity_available": 80.0,
            "unit": "Kits",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "owner": "DomainFilterTester",
            "location": {"address": "Central Medical Depot", "latitude": 28.6139, "longitude": 77.2090},
        },
        {
            "resource_id": "RES-TEST-WAT-01",
            "name": "Potable Water Supply Tanker",
            "resource_type": "Water",
            "category": "Potable Water",
            "quantity_total": 5000.0,
            "quantity_available": 4000.0,
            "unit": "Litres",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "owner": "DomainFilterTester",
            "location": {"address": "Municipal Water Staging", "latitude": 28.6139, "longitude": 77.2090},
        },
        {
            "resource_id": "RES-TEST-SHL-01",
            "name": "Sector 4 Evacuation Shelter",
            "resource_type": "Shelter",
            "category": "Emergency Shelter Facility",
            "quantity_total": 200.0,
            "quantity_available": 150.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "owner": "DomainFilterTester",
            "location": {"address": "Sector 4 Community Hall", "latitude": 28.6139, "longitude": 77.2090},
        },
    ]
    await db.resources.insert_many(test_docs)

    # 1. Query Fleet & Vehicles (Only Transport)
    res_fleet = await client.get("/api/v1/resources?resource_type=Transport", headers=rm_headers)
    assert res_fleet.status_code == 200
    fleet_items = res_fleet.json()["items"]
    assert any(r["resource_id"] == "RES-TEST-VEH-01" for r in fleet_items)
    assert all(r["resource_type"] == "Transport" for r in fleet_items)
    # Shelter, Medicine, and Water must NOT appear in Fleet
    assert not any(r["resource_id"] == "RES-TEST-SHL-01" for r in fleet_items)
    assert not any(r["resource_id"] == "RES-TEST-MED-01" for r in fleet_items)
    assert not any(r["resource_id"] == "RES-TEST-WAT-01" for r in fleet_items)

    # 2. Query Medical Supplies (Only Medicine, First Aid, Medical Equipment, Healthcare)
    res_med = await client.get(
        "/api/v1/resources?resource_types=Medicine&resource_types=First Aid&resource_types=Medical Equipment",
        headers=rm_headers,
    )
    assert res_med.status_code == 200
    med_items = res_med.json()["items"]
    assert any(r["resource_id"] == "RES-TEST-MED-01" for r in med_items)
    assert all(r["resource_type"] in ["Medicine", "First Aid", "Medical Equipment", "Healthcare"] for r in med_items)
    assert not any(r["resource_id"] == "RES-TEST-VEH-01" for r in med_items)
    assert not any(r["resource_id"] == "RES-TEST-SHL-01" for r in med_items)

    # 3. Query Rations & Water (Only Water and Food)
    res_water = await client.get(
        "/api/v1/resources?resource_types=Water&resource_types=Food",
        headers=rm_headers,
    )
    assert res_water.status_code == 200
    water_items = res_water.json()["items"]
    assert any(r["resource_id"] == "RES-TEST-WAT-01" for r in water_items)
    assert all(r["resource_type"] in ["Water", "Food"] for r in water_items)
    assert not any(r["resource_id"] == "RES-TEST-VEH-01" for r in water_items)

    # 4. Domain-specific stats for Transport
    res_fleet_stats = await client.get("/api/v1/resources/stats?resource_type=Transport", headers=rm_headers)
    assert res_fleet_stats.status_code == 200
    fleet_stats = res_fleet_stats.json()
    assert fleet_stats["total_resources"] >= 1
    assert "Transport" in fleet_stats["type_counts"]

    # 5. List all allocations endpoint
    res_alloc = await client.get("/api/v1/needs/allocations", headers=rm_headers)
    assert res_alloc.status_code == 200
    assert isinstance(res_alloc.json(), list)

    # Cleanup
    await db.resources.delete_many({"owner": "DomainFilterTester"})
