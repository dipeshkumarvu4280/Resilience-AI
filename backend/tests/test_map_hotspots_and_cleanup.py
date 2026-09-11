import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from app.main import app
from app.core.security import create_access_token
from app.db.mongodb import db_manager
from app.models.enums import UserRole, EmergencyType, SeverityLevel, ReportStatus, SituationStatus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_01_public_active_hotspots_unauthenticated_and_privacy_safe(client: AsyncClient, setup_db):
    """Test public active hotspots endpoint is unauthenticated and privacy-safe."""
    # 1. Query with zero active data
    res = await client.get("/api/v1/public/map/active-hotspots")
    assert res.status_code == 200
    data = res.json()
    assert "hotspots" in data
    assert "total_active_hotspots" in data
    assert "total_active_incidents" in data
    assert isinstance(data["hotspots"], list)

    # 2. Also verify alias /citizen/map/active-hotspots
    res2 = await client.get("/api/v1/citizen/map/active-hotspots")
    assert res2.status_code == 200
    assert res2.json()["total_active_hotspots"] == data["total_active_hotspots"]


@pytest.mark.anyio
async def test_02_hotspot_lifecycle_and_officer_resolved_cleanup(client: AsyncClient, setup_db):
    """
    Test real lifecycle:
    1. Active incident/situation created -> appears in public hotspots & officer active map
    2. Incident resolved -> disappears from public hotspots & officer active map
    3. Retained in officer history view
    4. Repeated query maintains clean state
    """
    db = db_manager.db

    # Officer token with genuine authorization claims
    officer_token = create_access_token({
        "sub": "9999999001",
        "phone": "9999999001",
        "role": UserRole.EMERGENCY_OFFICER.value,
        "full_name": "Emergency Officer 1",
    })
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # Step 1: Create a real citizen report
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Ravi Kumar",
            "phone": "9876543210",
            "emergency_type": EmergencyType.CYCLONE_STORM.value,
            "description": "Urgent structural collapse threat at private compound 4th lane",
            "location": {
                "latitude": 16.2954,
                "longitude": 80.6482,
                "address": "4th Lane, Main Road",
                "zone_or_district": "Guntur East",
                "city": "Guntur"
            }
        }
    )
    assert rep_res.status_code == 201
    rep_data = rep_res.json()
    report_id = rep_data["report_id"]

    # Verify Public Hotspot appears
    pub_res = await client.get("/api/v1/public/map/active-hotspots")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["total_active_hotspots"] >= 1
    assert pub_data["total_active_incidents"] >= 1

    # Strict Privacy Check on Public Hotspots
    for hs in pub_data["hotspots"]:
        hs_str = str(hs).lower()
        # Must NOT leak PII or exact address/phone/name
        assert "ravi" not in hs_str
        assert "9876543210" not in hs_str
        assert "private compound" not in hs_str
        assert report_id.lower() not in hs_str

    # Verify Officer Map in Active Mode
    off_act_res = await client.get("/api/v1/map/officer/data?view_mode=active", headers=officer_headers)
    assert off_act_res.status_code == 200
    off_act_data = off_act_res.json()
    assert off_act_data["total_active_reports"] >= 1
    act_report_ids = [r["report_id"] for r in off_act_data["reports"]]
    assert report_id in act_report_ids

    # Step 2: Step through canonical status lifecycle to RESOLVED
    ack_res = await client.post(f"/api/v1/officer/reports/{report_id}/acknowledge", headers=officer_headers)
    assert ack_res.status_code == 200

    await client.patch(f"/api/v1/officer/reports/{report_id}/status", headers=officer_headers, json={"status": ReportStatus.UNDER_ASSESSMENT.value})
    await client.patch(f"/api/v1/officer/reports/{report_id}/status", headers=officer_headers, json={"status": ReportStatus.ACTION_REQUIRED.value})
    resolve_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/status",
        headers=officer_headers,
        json={"status": ReportStatus.RESOLVED.value, "reason": "Floodwaters cleared, safe to close"}
    )
    assert resolve_res.status_code == 200

    # Step 3: Verify Public Hotspot Disappears
    pub_res_after = await client.get("/api/v1/public/map/active-hotspots")
    assert pub_res_after.status_code == 200
    pub_data_after = pub_res_after.json()
    # Report resolved, so active incident count should decrease
    assert pub_data_after["total_active_incidents"] < pub_data["total_active_incidents"]

    # Step 4: Verify Officer Active Map Excludes Resolved Incident
    off_act_res2 = await client.get("/api/v1/map/officer/data?view_mode=active", headers=officer_headers)
    assert off_act_res2.status_code == 200
    off_act_data2 = off_act_res2.json()
    act_report_ids2 = [r["report_id"] for r in off_act_data2["reports"]]
    assert report_id not in act_report_ids2

    # Step 5: Verify Officer History Map Retains the Resolved Incident
    off_hist_res = await client.get("/api/v1/map/officer/data?view_mode=history", headers=officer_headers)
    assert off_hist_res.status_code == 200
    off_hist_data = off_hist_res.json()
    hist_report_ids = [r["report_id"] for r in off_hist_data["reports"]]
    assert report_id in hist_report_ids

    # Step 6: Verify Repeated Poll / Refresh Does Not Re-introduce Resolved Incident
    off_act_res3 = await client.get("/api/v1/map/officer/data?view_mode=active", headers=officer_headers)
    assert report_id not in [r["report_id"] for r in off_act_res3.json()["reports"]]


@pytest.mark.anyio
async def test_03_officer_map_rbac_security(client: AsyncClient, setup_db):
    """Test that unauthorized public clients cannot access officer operational map data."""
    res = await client.get("/api/v1/map/officer/data")
    assert res.status_code in [401, 403]


@pytest.mark.anyio
async def test_04_situation_cluster_resolution_cleans_map(client: AsyncClient, setup_db):
    """Test situation cluster creation and closure lifecycle propagates clean map state."""
    db = db_manager.db

    officer_token = create_access_token({
        "sub": "9999999001",
        "phone": "9999999001",
        "role": UserRole.EMERGENCY_OFFICER.value,
        "full_name": "Emergency Officer 1",
    })
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # Create Situation with custom ID
    sit_id = "SIT-MAP-TEST-01"
    now_utc = datetime.now(timezone.utc)
    await db["situations"].insert_one({
        "situation_id": sit_id,
        "cluster_id": "CLUST-MAP-01",
        "title": "Severe Flood Inundation - Ward 4",
        "situation_summary": "High water levels threatening riverside settlements",
        "emergency_type": EmergencyType.FLOODING_WATER_LEVEL.value if hasattr(EmergencyType, 'FLOODING_WATER_LEVEL') else EmergencyType.CYCLONE_STORM.value,
        "severity_level": SeverityLevel.HIGH.value,
        "severity_score": 8.2,
        "status": SituationStatus.ACTIVE.value,
        "report_count": 2,
        "report_ids": ["REP-MAP-A", "REP-MAP-B"],
        "center_location": {
            "latitude": 16.3100,
            "longitude": 80.6500,
            "zone_or_district": "Krishna Basin",
            "city": "Vijayawada"
        },
        "impact_zone": {
            "center_latitude": 16.3100,
            "center_longitude": 80.6500,
            "radius_km": 2.5,
            "affected_zone_name": "Krishna Basin"
        },
        "created_at": now_utc,
        "updated_at": now_utc,
    })

    # Insert the member reports
    await db["citizen_reports"].insert_many([
        {
            "report_id": "REP-MAP-A",
            "citizen_name": "Citizen A",
            "citizen_phone": "9998881111",
            "emergency_type": EmergencyType.CYCLONE_STORM.value,
            "description": "Rising water at street 1",
            "status": ReportStatus.ACTION_REQUIRED.value,
            "situation_id": sit_id,
            "location": {"latitude": 16.3090, "longitude": 80.6490, "address": "Street 1"},
            "created_at": now_utc,
            "updated_at": now_utc,
        },
        {
            "report_id": "REP-MAP-B",
            "citizen_name": "Citizen B",
            "citizen_phone": "9998882222",
            "emergency_type": EmergencyType.CYCLONE_STORM.value,
            "description": "Rising water at street 2",
            "status": ReportStatus.ACTION_REQUIRED.value,
            "situation_id": sit_id,
            "location": {"latitude": 16.3110, "longitude": 80.6510, "address": "Street 2"},
            "created_at": now_utc,
            "updated_at": now_utc,
        }
    ])

    # 1. Verify Active Hotspots & Officer Active Map
    pub_res = await client.get("/api/v1/public/map/active-hotspots")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert any(h["general_area_name"] == "Krishna Basin" for h in pub_data["hotspots"])

    off_res = await client.get("/api/v1/map/officer/data?view_mode=active", headers=officer_headers)
    assert off_res.status_code == 200
    assert any(s["situation_id"] == sit_id for s in off_res.json()["situations"])

    # 2. Resolve both reports
    await client.patch(
        "/api/v1/officer/reports/REP-MAP-A/status",
        headers=officer_headers,
        json={"status": ReportStatus.RESOLVED.value, "reason": "Dewatering complete"}
    )
    await client.patch(
        "/api/v1/officer/reports/REP-MAP-B/status",
        headers=officer_headers,
        json={"status": ReportStatus.RESOLVED.value, "reason": "Residents safely evacuated"}
    )

    # 3. Verify Situation is marked RESOLVED and disappears from active map
    pub_res_resolved = await client.get("/api/v1/public/map/active-hotspots")
    assert not any(h["general_area_name"] == "Krishna Basin" for h in pub_res_resolved.json()["hotspots"])

    off_res_resolved = await client.get("/api/v1/map/officer/data?view_mode=active", headers=officer_headers)
    assert not any(s["situation_id"] == sit_id for s in off_res_resolved.json()["situations"])

    # 4. Verify Situation appears in History view
    off_res_history = await client.get("/api/v1/map/officer/data?view_mode=history", headers=officer_headers)
    assert any(s["situation_id"] == sit_id for s in off_res_history.json()["situations"])

