import pytest
import uuid
from httpx import AsyncClient
from app.models.enums import UserRole


@pytest.mark.anyio
async def test_resource_manager_create_and_manage_inventory(client: AsyncClient):
    """Scenarios 1-4: Resource Manager creates, updates, adjusts quantity, and changes status."""
    # 1. Login as Resource Manager (Elena Rostova)
    login_res = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999003",
            "password": "ResourcePassword@2026",
            "intended_role": "RESOURCE_MANAGER",
        },
    )
    assert login_res.status_code == 200, login_res.text
    rm_token = login_res.json()["access_token"]
    rm_headers = {"Authorization": f"Bearer {rm_token}"}

    # 2. Create a real emergency resource
    create_payload = {
        "name": "Central Emergency Water Reserve",
        "resource_type": "Water",
        "category": "Potable Drinking Water",
        "quantity_total": 500,
        "quantity_available": 500,
        "unit": "liters",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Sector 4 Logistics Hub, Vijayawada",
            "zone_or_district": "Krishna District",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
        },
        "status": "AVAILABLE",
        "condition": "GOOD",
        "owner": "National Disaster Management Authority",
        "contact": "+91 98765 43210",
        "notes": "Emergency bottled mineral water ready for dispatch.",
    }

    res = await client.post("/api/v1/resources", json=create_payload, headers=rm_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["resource_id"].startswith("RES-")
    assert data["name"] == "Central Emergency Water Reserve"
    assert data["quantity_available"] == 500
    assert data["created_by_name"] == "Elena Rostova"
    resource_id = data["resource_id"]

    # 3. Update Resource Details
    update_payload = {
        "notes": "Updated: Inspected and certified by logistics officer.",
        "condition": "GOOD",
    }
    res_update = await client.patch(f"/api/v1/resources/{resource_id}", json=update_payload, headers=rm_headers)
    assert res_update.status_code == 200
    assert "Inspected and certified" in res_update.json()["notes"]

    # 4. Update Quantity (Stock adjustment)
    qty_payload = {
        "quantity_available": 450,
        "quantity_total": 500,
        "reason": "Dispatched 50 liters for local training drill",
    }
    res_qty = await client.patch(f"/api/v1/resources/{resource_id}/quantity", json=qty_payload, headers=rm_headers)
    assert res_qty.status_code == 200
    assert res_qty.json()["quantity_available"] == 450

    # 5. Change Status
    status_payload = {
        "status": "PARTIALLY_AVAILABLE",
        "reason": "High demand in nearby sector",
    }
    res_status = await client.patch(f"/api/v1/resources/{resource_id}/status", json=status_payload, headers=rm_headers)
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "PARTIALLY_AVAILABLE"


@pytest.mark.anyio
async def test_resource_validation_rules(client: AsyncClient):
    """Verify backend enforces strict validation: no negative quantities, no available > total, valid coordinates."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999003",
            "password": "ResourcePassword@2026",
            "intended_role": "RESOURCE_MANAGER",
        },
    )
    assert login_res.status_code == 200
    rm_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Negative quantity
    bad_qty_payload = {
        "name": "Invalid Resource",
        "resource_type": "Water",
        "quantity_total": -10,
        "quantity_available": -10,
        "unit": "liters",
        "location": {"latitude": 16.5, "longitude": 80.6},
    }
    res = await client.post("/api/v1/resources", json=bad_qty_payload, headers=rm_headers)
    assert res.status_code == 422

    # Available > Total
    bad_avail_payload = {
        "name": "Invalid Overflow Resource",
        "resource_type": "Water",
        "quantity_total": 100,
        "quantity_available": 150,
        "unit": "liters",
        "location": {"latitude": 16.5, "longitude": 80.6},
    }
    res2 = await client.post("/api/v1/resources", json=bad_avail_payload, headers=rm_headers)
    assert res2.status_code == 422

    # Invalid Coordinates
    bad_coord_payload = {
        "name": "Invalid Location Resource",
        "resource_type": "Water",
        "quantity_total": 100,
        "quantity_available": 100,
        "unit": "liters",
        "location": {"latitude": 999.0, "longitude": 80.6},
    }
    res3 = await client.post("/api/v1/resources", json=bad_coord_payload, headers=rm_headers)
    assert res3.status_code == 422


@pytest.mark.anyio
async def test_resource_rbac_permissions(client: AsyncClient):
    """Scenarios 5-7: RBAC controls for Resources."""
    # Officer login
    officer_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert officer_login.status_code == 200
    officer_token = officer_login.json()["access_token"]
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # Officer can READ resources
    res_list = await client.get("/api/v1/resources", headers=officer_headers)
    assert res_list.status_code == 200

    # Officer CANNOT CREATE resources
    create_payload = {
        "name": "Officer Unauthorized Resource",
        "resource_type": "Food",
        "quantity_total": 50,
        "quantity_available": 50,
        "unit": "meals",
        "location": {"latitude": 16.5, "longitude": 80.6},
    }
    res_create = await client.post("/api/v1/resources", json=create_payload, headers=officer_headers)
    assert res_create.status_code == 403


@pytest.mark.anyio
async def test_officer_needs_assessment_and_ai_suggestions(client: AsyncClient):
    """Scenarios 8-11 & 25-28: Needs Assessment CRUD, AI Suggestions, Human Review."""
    # Login Officer
    login_res = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert login_res.status_code == 200
    officer_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # First, submit a real citizen report
    phone = f"987{uuid.uuid4().int % 10000000:07d}"
    report_payload = {
        "full_name": "Ramesh Verma",
        "phone": phone,
        "emergency_type": "Flood",
        "description": "Severe flooding in residential block. 40 families stranded without clean drinking water and food rations.",
        "location": {
            "latitude": 16.5100,
            "longitude": 80.6500,
            "address": "Bhavanipuram Flood Relief Zone",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
        },
        "media": [],
    }
    report_res = await client.post("/api/v1/citizen/reports", json=report_payload)
    assert report_res.status_code == 201, report_res.text
    report_id = report_res.json()["report_id"]

    # 1. AI Needs Suggestion
    ai_res = await client.post(f"/api/v1/officer/reports/{report_id}/ai/needs-suggestion", headers=officer_headers)
    assert ai_res.status_code == 200
    ai_data = ai_res.json()
    assert "suggestions" in ai_data
    assert "disclaimer" in ai_data
    assert len(ai_data["suggestions"]) > 0
    assert any(s["resource_type"] in ["Water", "Food", "Rescue Equipment"] for s in ai_data["suggestions"])

    # 2. Officer Creates Structured Needs Assessment
    needs_payload = {
        "needs": [
            {
                "need_id": "NEED-W01",
                "resource_type": "Water",
                "requested_quantity": 100,
                "unit": "liters",
                "urgency": "HIGH",
                "reason": "Drinking water for stranded residents",
            },
            {
                "need_id": "NEED-F01",
                "resource_type": "Food",
                "requested_quantity": 40,
                "unit": "meals",
                "urgency": "HIGH",
                "reason": "Emergency ration packets",
            },
        ]
    }
    save_needs_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/needs",
        json=needs_payload,
        headers=officer_headers,
    )
    assert save_needs_res.status_code == 200
    saved_needs = save_needs_res.json()
    assert len(saved_needs["needs"]) == 2
    assert saved_needs["assessed_by"] in ["Officer Marcus Vance", "Dipesh Kumar"]

    # 3. Read Needs
    get_needs_res = await client.get(f"/api/v1/officer/reports/{report_id}/needs", headers=officer_headers)
    assert get_needs_res.status_code == 200
    assert len(get_needs_res.json()["needs"]) == 2

    # 4. Invalid Quantity in Needs rejected
    bad_needs = {
        "needs": [
            {
                "need_id": "BAD-1",
                "resource_type": "Water",
                "requested_quantity": -5,
                "unit": "liters",
                "urgency": "LOW",
            }
        ]
    }
    bad_res = await client.post(f"/api/v1/officer/reports/{report_id}/needs", json=bad_needs, headers=officer_headers)
    assert bad_res.status_code == 422


@pytest.mark.anyio
async def test_deterministic_matching_and_allocation_workflow(client: AsyncClient):
    """Scenarios 12-24: Resource Matching, Propose, Approve, Atomic Decrement & Audit."""
    # Resource Manager login to register resources
    rm_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999003",
            "password": "ResourcePassword@2026",
            "intended_role": "RESOURCE_MANAGER",
        },
    )
    assert rm_login.status_code == 200
    rm_headers = {"Authorization": f"Bearer {rm_login.json()['access_token']}"}

    # Officer login
    officer_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert officer_login.status_code == 200
    officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}

    # Create two warehouses with Generator stock (60 units in Depot A, 80 units in Depot B)
    res_a_payload = {
        "name": "Generator Hub Alpha",
        "resource_type": "Generator",
        "category": "Heavy Diesel Power",
        "quantity_total": 60,
        "quantity_available": 60,
        "unit": "units",
        "location": {
            "latitude": 16.5120,
            "longitude": 80.6520,
            "address": "North Sector Depot",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
        },
        "status": "AVAILABLE",
        "condition": "GOOD",
    }
    res_a = await client.post("/api/v1/resources", json=res_a_payload, headers=rm_headers)
    assert res_a.status_code == 201
    res_a_id = res_a.json()["resource_id"]

    res_b_payload = {
        "name": "Generator Hub Beta",
        "resource_type": "Generator",
        "category": "Heavy Diesel Power",
        "quantity_total": 80,
        "quantity_available": 80,
        "unit": "units",
        "location": {
            "latitude": 16.5200,
            "longitude": 80.6600,
            "address": "East Sector Depot",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
        },
        "status": "AVAILABLE",
        "condition": "GOOD",
    }
    res_b = await client.post("/api/v1/resources", json=res_b_payload, headers=rm_headers)
    assert res_b.status_code == 201
    res_b_id = res_b.json()["resource_id"]

    # Create Report
    phone = f"987{uuid.uuid4().int % 10000000:07d}"
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Anita Rao",
            "phone": phone,
            "emergency_type": "Cyclone / Storm",
            "description": "Grid power down in entire relief camp. Need 100 emergency generators.",
            "location": {"latitude": 16.5100, "longitude": 80.6500, "city": "Vijayawada"},
            "media": [],
        },
    )
    assert rep_res.status_code == 201
    report_id = rep_res.json()["report_id"]

    # Set Need: 100 units of Generator
    await client.post(
        f"/api/v1/officer/reports/{report_id}/needs",
        json={
            "needs": [
                {
                    "need_id": "NEED-GEN-100",
                    "resource_type": "Generator",
                    "requested_quantity": 100,
                    "unit": "units",
                    "urgency": "CRITICAL",
                }
            ]
        },
        headers=officer_headers,
    )

    # 1. Run Resource Matching
    match_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/resource-matching",
        headers=officer_headers,
    )
    assert match_res.status_code == 200
    match_data = match_res.json()
    assert len(match_data["needs_matches"]) == 1
    gen_match = match_data["needs_matches"][0]
    assert gen_match["requested_quantity"] == 100
    assert gen_match["is_fully_matchable"] is True
    assert len(gen_match["candidates"]) == 2

    # Verify candidate scoring, distance and recommended split (60 from Hub Alpha, 40 from Hub Beta)
    cand_a = next(c for c in gen_match["candidates"] if c["resource_id"] == res_a_id)
    assert cand_a["match_score"] > 0
    assert cand_a["distance_km"] >= 0
    assert cand_a["recommended_allocation"] == 60

    cand_b = next(c for c in gen_match["candidates"] if c["resource_id"] == res_b_id)
    assert cand_b["recommended_allocation"] == 40

    # 2. Propose Allocation for Depot Alpha (60 units)
    prop_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/allocations",
        json={
            "need_id": "NEED-GEN-100",
            "resource_id": res_a_id,
            "requested_quantity": 60,
            "notes": "Allocated from closest depot",
        },
        headers=officer_headers,
    )
    assert prop_res.status_code == 201
    alloc_a_id = prop_res.json()["allocation_id"]
    assert prop_res.json()["status"] == "PROPOSED"

    # 3. Approve Allocation -> Atomic inventory decrement
    appr_res = await client.post(
        f"/api/v1/officer/allocations/{alloc_a_id}/approve",
        headers=officer_headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"
    assert appr_res.json()["approved_quantity"] == 60
    assert appr_res.json()["approved_by"] in ["Officer Marcus Vance", "Dipesh Kumar"]

    # Verify Depot Alpha inventory decreased from 60 to 0
    res_a_check = await client.get(f"/api/v1/resources/{res_a_id}", headers=rm_headers)
    assert res_a_check.json()["quantity_available"] == 0
    assert res_a_check.json()["status"] == "UNAVAILABLE"

    # 4. Attempt to over-allocate beyond stock -> rejected safely
    over_prop = await client.post(
        f"/api/v1/officer/reports/{report_id}/allocations",
        json={
            "need_id": "NEED-GEN-100",
            "resource_id": res_a_id,
            "requested_quantity": 10,
        },
        headers=officer_headers,
    )
    assert over_prop.status_code == 400
    assert "exceeds available stock" in over_prop.json()["detail"]

    # 5. Propose Allocation for Depot Beta (40 units) and then Reject
    prop_b = await client.post(
        f"/api/v1/officer/reports/{report_id}/allocations",
        json={
            "need_id": "NEED-GEN-100",
            "resource_id": res_b_id,
            "requested_quantity": 40,
        },
        headers=officer_headers,
    )
    assert prop_b.status_code == 201
    alloc_b_id = prop_b.json()["allocation_id"]

    rej_res = await client.post(
        f"/api/v1/officer/allocations/{alloc_b_id}/reject",
        json={"reason": "Officer re-routing to different facility"},
        headers=officer_headers,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    # Verify Depot Beta inventory was NOT decremented
    res_b_check = await client.get(f"/api/v1/resources/{res_b_id}", headers=rm_headers)
    assert res_b_check.json()["quantity_available"] == 80


@pytest.mark.anyio
async def test_audit_trail_for_phase3(client: AsyncClient):
    """Scenarios 29-35: Audit events logged for Phase 3 operations with authenticated actor attribution."""
    # Officer login
    officer_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert officer_login.status_code == 200
    officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}

    # Create report and check timeline
    phone = f"987{uuid.uuid4().int % 10000000:07d}"
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Suresh Babu",
            "phone": phone,
            "emergency_type": "Fire",
            "description": "Factory fire emergency requiring foam and water tenders.",
            "location": {"latitude": 16.505, "longitude": 80.645, "city": "Vijayawada"},
            "media": [],
        },
    )
    assert rep_res.status_code == 201
    report_id = rep_res.json()["report_id"]

    # Assess Needs
    await client.post(
        f"/api/v1/officer/reports/{report_id}/needs",
        json={
            "needs": [
                {
                    "need_id": "NEED-FIRE-1",
                    "resource_type": "Rescue Equipment",
                    "requested_quantity": 2,
                    "unit": "units",
                    "urgency": "CRITICAL",
                }
            ]
        },
        headers=officer_headers,
    )

    # Inspect Report Detail and Timeline
    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=officer_headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    
    # Verify timeline contains NEEDS_ASSESSED
    event_types = [evt["event_type"] for evt in detail["timeline"]]
    assert "NEEDS_ASSESSED" in event_types

    # Verify actor is a legitimate authenticated officer (not synthetic or default placeholder)
    needs_event = next(evt for evt in detail["timeline"] if evt["event_type"] == "NEEDS_ASSESSED")
    assert needs_event["actor_name"] in ["Officer Marcus Vance", "Dipesh Kumar"]
    assert needs_event["actor_role"] == UserRole.EMERGENCY_OFFICER.value
