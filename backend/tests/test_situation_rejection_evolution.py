import pytest
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.db.mongodb import db_manager
from app.models.enums import ReportStatus, SituationStatus, SeverityLevel, EmergencyType
from app.services.incident_fusion import fuse_or_create_situation_for_report, refresh_situation_cluster


async def get_auth_headers(client: AsyncClient, phone: str = "9999999002", password: str = "OfficerPassword@2026") -> Dict[str, str]:
    """Helper to login and return JWT Authorization headers."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": password},
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_citizen_report(
    report_id: str,
    status: str = "RECEIVED",
    emergency_type: str = "Flood",
    latitude: float = 16.5062,
    longitude: float = 80.6480,
    situation_id: str = None,
) -> Dict[str, Any]:
    """Helper to insert a genuine citizen report for testing."""
    db = db_manager.db
    now = datetime.now(timezone.utc)
    doc = {
        "report_id": report_id,
        "citizen_id": f"CITIZEN-{report_id}",
        "citizen_name": f"Citizen {report_id}",
        "citizen_phone": "+919999999001",
        "emergency_type": emergency_type,
        "citizen_impact_level": "HIGH",
        "description": f"Verified test report for incident {report_id}",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "address": "Benz Circle, Vijayawada",
            "zone_or_district": "Krishna District",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "country": "India",
        },
        "media": [],
        "status": status,
        "priority": "HIGH",
        "phone_verified": True,
        "risk_level": "LOW",
        "trust_state": "VERIFIED",
        "trust_signals": ["DEVICE_GPS_VERIFIED"],
        "situation_id": situation_id,
        "timeline": [
            {
                "event_id": f"EVT-INIT-{report_id}",
                "event_type": "REPORT_RECEIVED",
                "timestamp": now,
                "details": f"Emergency report {report_id} received.",
                "actor_id": f"CITIZEN-{report_id}",
                "actor_name": f"Citizen {report_id}",
                "actor_role": "CITIZEN",
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    await db["citizen_reports"].update_one(
        {"report_id": report_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


@pytest.mark.anyio
async def test_multi_report_situation_recomputes_on_rejection(client: AsyncClient):
    """
    Scenario 2: Multi-report situation (R1, R2, R3).
    When officer rejects R2, the situation cluster recomputes using only R1 + R3.
    R2 is excluded from report count, severity, and active member list.
    """
    db = db_manager.db
    r1_id = "RES-MULTI-R1"
    r2_id = "RES-MULTI-R2"
    r3_id = "RES-MULTI-R3"

    r1 = await create_test_citizen_report(r1_id, status="RECEIVED", latitude=16.5062, longitude=80.6480)
    r2 = await create_test_citizen_report(r2_id, status="RECEIVED", latitude=16.5070, longitude=80.6490)
    r3 = await create_test_citizen_report(r3_id, status="RECEIVED", latitude=16.5080, longitude=80.6500)

    # Fuse reports into one situation
    sit1 = await fuse_or_create_situation_for_report(db, r1)
    sit_id = sit1["situation_id"]
    await fuse_or_create_situation_for_report(db, r2)
    await fuse_or_create_situation_for_report(db, r3)

    # Verify initial situation has 3 reports
    sit_doc = await db["situations"].find_one({"situation_id": sit_id})
    assert sit_doc is not None
    assert set(sit_doc["report_ids"]) == {r1_id, r2_id, r3_id}
    assert sit_doc["report_count"] == 3

    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    # Reject R2 with descriptive reason
    reject_reason = "Duplicate call from caller regarding the same flooded intersection already monitored."
    res = await client.post(
        f"/api/v1/officer/reports/{r2_id}/reject",
        headers=officer_headers,
        json={"reason": reject_reason},
    )
    assert res.status_code == 200

    # Verify situation recomputed to 2 reports (R1 and R3)
    updated_sit = await db["situations"].find_one({"situation_id": sit_id})
    assert updated_sit is not None
    assert r2_id not in updated_sit["report_ids"]
    assert set(updated_sit["report_ids"]) == {r1_id, r3_id}
    assert updated_sit["report_count"] == 2
    assert updated_sit["status"] == SituationStatus.ACTIVE.value

    # Verify get_situation_detail endpoint returns only active reports
    detail_res = await client.get(
        f"/api/v1/officer/situations/{sit_id}",
        headers=officer_headers,
    )
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    clustered_ids = [r["report_id"] for r in detail_data["clustered_reports"]]
    assert r2_id not in clustered_ids
    assert set(clustered_ids) == {r1_id, r3_id}


@pytest.mark.anyio
async def test_single_report_situation_transitions_to_closed_on_rejection(client: AsyncClient):
    """
    Scenario 1 & 4: Single-report situation (R1).
    When officer rejects R1, the situation has 0 eligible reports left.
    The situation transitions to CLOSED and is permanently excluded from active SI feeds.
    """
    db = db_manager.db
    r1_id = "RES-SOLO-R1"
    r1 = await create_test_citizen_report(r1_id, status="RECEIVED", emergency_type="Medical Emergency")

    sit = await fuse_or_create_situation_for_report(db, r1)
    sit_id = sit["situation_id"]

    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    # Reject R1
    reason = "False alarm: accidental panic trigger confirmed with caller."
    res = await client.post(
        f"/api/v1/officer/reports/{r1_id}/reject",
        headers=officer_headers,
        json={"reason": reason},
    )
    assert res.status_code == 200

    # Verify situation state in DB
    updated_sit = await db["situations"].find_one({"situation_id": sit_id})
    assert updated_sit is not None
    assert updated_sit["report_count"] == 0
    assert updated_sit["report_ids"] == []
    assert updated_sit["status"] == SituationStatus.CLOSED.value

    # Verify situation is excluded from active situations list endpoint
    list_res = await client.get("/api/v1/officer/situations", headers=officer_headers)
    assert list_res.status_code == 200
    active_sits = list_res.json()["items"]
    assert not any(s["situation_id"] == sit_id for s in active_sits)

    # Verify stats endpoint does not count 0-report situation in active count
    stats_res = await client.get("/api/v1/officer/situations/stats", headers=officer_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    # Active situations in stats must be greater than or equal to active items in list
    assert stats["active_situations"] == len(active_sits)


@pytest.mark.anyio
async def test_incident_evolution_timeline_endpoint_and_rejection_audit(client: AsyncClient):
    """
    Scenario 7 & 8: Incident Evolution Timeline loads correctly for situation and report,
    surfaces genuine REPORT_REJECTED audit events with officer reason, and does not return 404.
    """
    db = db_manager.db
    report_id = "RES-TL-REJ-01"
    report_doc = await create_test_citizen_report(report_id, status="RECEIVED")

    sit = await fuse_or_create_situation_for_report(db, report_doc)
    sit_id = sit["situation_id"]

    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    # Reject report
    rejection_reason = "Operational rejection: Outside designated sector zone."
    rej_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": rejection_reason},
    )
    assert rej_res.status_code == 200

    # Test Situation Evolution Timeline on /api/v1/officer/situations/{id}/evolution-timeline
    tl_res1 = await client.get(
        f"/api/v1/officer/situations/{sit_id}/evolution-timeline",
        headers=officer_headers,
    )
    assert tl_res1.status_code == 200
    tl_data1 = tl_res1.json()
    assert tl_data1["target_id"] == sit_id
    assert tl_data1["total_events"] > 0
    # Must contain the rejection event
    rej_events = [e for e in tl_data1["events"] if "REJECT" in e["event_type"].upper()]
    assert len(rej_events) >= 1
    assert rejection_reason in rej_events[0]["details"] or rejection_reason in rej_events[0]["summary"]

    # Test Situation Evolution Timeline alias on /api/v1/situations/{id}/evolution-timeline
    tl_res2 = await client.get(
        f"/api/v1/situations/{sit_id}/evolution-timeline",
        headers=officer_headers,
    )
    assert tl_res2.status_code == 200
    assert tl_res2.json()["target_id"] == sit_id

    # Test Report Evolution Timeline on /api/v1/citizen/reports/{id}/evolution-timeline
    tl_res3 = await client.get(
        f"/api/v1/citizen/reports/{report_id}/evolution-timeline",
        headers=officer_headers,
    )
    assert tl_res3.status_code == 200
    assert tl_res3.json()["target_id"] == report_id


@pytest.mark.anyio
async def test_rejection_web_push_payload_contains_actual_reason(client: AsyncClient):
    """
    Scenario 9 & 10: Rejection Web Push notification payload contains the actual reason entered by the officer.
    """
    db = db_manager.db
    report_id = "RES-PUSH-REASON-01"
    await create_test_citizen_report(report_id, status="RECEIVED")

    # Add active push subscription
    now = datetime.now(timezone.utc)
    endpoint = "https://fcm.googleapis.com/fcm/send/test-sub-reason-token"
    await db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-TEST-REASON-01",
        "endpoint": endpoint,
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVYOSTxGen0KURo6ISVA27LT3",
        "auth": "tBHItJI5svbpez7KI4CCXg",
        "user_id": None,
        "role": "CITIZEN",
        "status": "ACTIVE",
        "report_ids": [report_id],
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    })

    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    exact_reason = "Road blockage cleared by municipality maintenance crew prior to responder arrival."

    with patch(
        "app.services.notification.web_push_service.WebPushService.send_web_push",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/reject",
            headers=officer_headers,
            json={"reason": exact_reason},
        )
        assert res.status_code == 200
        assert mock_send.await_count >= 1

        # Verify the payload passed to send_web_push contains the actual rejection reason
        call_args = mock_send.call_args
        payload_arg = call_args[0][1]
        assert exact_reason in payload_arg.body
        assert payload_arg.data.get("rejection_reason") == exact_reason
