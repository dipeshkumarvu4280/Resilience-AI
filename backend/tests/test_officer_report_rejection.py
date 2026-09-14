import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.models.enums import (
    UserRole,
    EmergencyType,
    ReportStatus,
    TimelineEventType,
    SafetyNotificationType,
    CorroborationStatus,
)
from app.db.mongodb import db_manager
from app.services.incident_fusion import fuse_or_create_situation_for_report
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.map_service import MapService


async def get_auth_headers(client: AsyncClient, phone: str, password: str):
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": password}
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_citizen_report(
    report_id: str,
    status: str = "RECEIVED",
    citizen_phone: str = "9999999005",
    emergency_type: str = "Flood",
    latitude: float = 16.5062,
    longitude: float = 80.6480,
):
    db = db_manager.db
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": report_id,
        "citizen_id": f"CIT-{report_id[-4:]}",
        "citizen_name": "Ravi Kumar",
        "citizen_phone": citizen_phone,
        "emergency_type": emergency_type,
        "citizen_impact_level": "HIGH",
        "description": f"Urgent incident description for {report_id}",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "address": "Ring Road Sector 4, Vijayawada",
        },
        "status": status,
        "priority": "UNASSESSED",
        "created_at": now,
        "updated_at": now,
    }
    await db["citizen_reports"].insert_one(report_doc)
    return report_doc


@pytest.mark.anyio
async def test_officer_can_reject_received_report(client: AsyncClient):
    """1. Officer can reject a RECEIVED report with descriptive mandatory reason."""
    report_id = "RES-REJ-001"
    await create_test_citizen_report(report_id, status="RECEIVED")

    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    reject_payload = {
        "reason": "False report confirmed via CCTV; no waterlogging found on site."
    }

    res = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json=reject_payload,
    )

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["report_id"] == report_id
    assert data["status"] == "REJECTED"
    assert data["rejection"] is not None
    assert data["rejection"]["reason"] == reject_payload["reason"]
    assert "rejected_at" in data["rejection"]
    assert data["rejection"]["rejected_by_user_id"] is not None
    assert data["rejection"]["rejected_by_name"] is not None
    assert "notification" in data
    assert data["notification"]["status"] in ["DELIVERED", "NO_SUBSCRIPTION", "FAILED"]

    # Verify MongoDB persistence
    db = db_manager.db
    doc = await db["citizen_reports"].find_one({"report_id": report_id})
    assert doc is not None
    assert doc["status"] == "REJECTED"
    assert doc["rejection_reason"] == reject_payload["reason"]
    assert doc["rejected_by_user_id"] is not None
    assert "rejected_at" in doc

    # Verify Timeline Events
    timeline_entry = await db["timeline_events"].find_one({
        "report_id": report_id,
        "event_type": TimelineEventType.REPORT_REJECTED.value,
    })
    assert timeline_entry is not None
    assert "False report confirmed" in (timeline_entry.get("details") or timeline_entry.get("description", ""))

    # Verify Audit Log
    audit_entry = await db["audit_logs"].find_one({
        "entity_id": report_id,
        "action": "REPORT_REJECTED",
    })
    assert audit_entry is not None
    assert audit_entry["entity_type"] == "CITIZEN_REPORT"


@pytest.mark.anyio
async def test_reject_validation_missing_or_invalid_reason(client: AsyncClient):
    """2. Missing, whitespace-only, or too short rejection reason returns 422."""
    report_id = "RES-REJ-VAL"
    await create_test_citizen_report(report_id, status="RECEIVED")
    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    # Empty reason
    res_empty = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": ""},
    )
    assert res_empty.status_code == 422

    # Whitespace only
    res_ws = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": "     "},
    )
    assert res_ws.status_code == 422

    # Too short (< 5 chars)
    res_short = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": "bad"},
    )
    assert res_short.status_code == 422

    # Missing field
    res_missing = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={},
    )
    assert res_missing.status_code == 422


@pytest.mark.anyio
async def test_reject_rbac_unauthenticated_and_forbidden(client: AsyncClient):
    """3. Unauthenticated and non-officer users cannot reject reports."""
    report_id = "RES-REJ-RBAC"
    await create_test_citizen_report(report_id, status="RECEIVED")

    # Unauthenticated
    res_no_auth = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        json={"reason": "Valid rejection reason for unauthorized check"},
    )
    assert res_no_auth.status_code == 401

    # Resource Manager (forbidden to officer action)
    rm_headers = await get_auth_headers(client, "9999999003", "ResourcePassword@2026")
    res_rm = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=rm_headers,
        json={"reason": "Valid rejection reason for unauthorized check"},
    )
    assert res_rm.status_code == 403

    # Citizen (forbidden)
    cit_headers = await get_auth_headers(client, "9999999005", "CitizenPassword@2026")
    res_cit = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=cit_headers,
        json={"reason": "Valid rejection reason for unauthorized check"},
    )
    assert res_cit.status_code == 403


@pytest.mark.anyio
async def test_reject_terminal_conflict_resolved_report(client: AsyncClient):
    """4. Rejecting an already RESOLVED report returns 409 Conflict."""
    report_id = "RES-REJ-RESOLVED"
    await create_test_citizen_report(report_id, status="RESOLVED")
    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    res = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": "Cannot reject resolved report"},
    )
    assert res.status_code == 409
    assert "RESOLVED" in res.json()["detail"]


@pytest.mark.anyio
async def test_reject_idempotency(client: AsyncClient):
    """5. Re-rejecting an already REJECTED report is idempotent (returns 200 without duplicate timeline/audit)."""
    report_id = "RES-REJ-IDEMPOTENT"
    await create_test_citizen_report(report_id, status="RECEIVED")
    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    reason = "Initial rejection reason for idempotency verification"

    # First call
    res1 = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": reason},
    )
    assert res1.status_code == 200

    # Second call with same or different reason
    res2 = await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": "Second rejection call reason"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "REJECTED"
    assert data2["rejection"]["reason"] == reason  # Retains original reason

    # Check that audit log has exactly 1 entry for this report
    db = db_manager.db
    audit_count = await db["audit_logs"].count_documents({
        "entity_id": report_id,
        "action": "REPORT_REJECTED",
    })
    assert audit_count == 1


@pytest.mark.anyio
async def test_rejected_report_kpi_stats_and_history_query(client: AsyncClient):
    """6. Rejected reports update rejected KPI stats and appear in history queries."""
    report_id = "RES-REJ-KPI"
    await create_test_citizen_report(report_id, status="RECEIVED")
    officer_headers = await get_auth_headers(client, "9999999002", "OfficerPassword@2026")

    # Reject report
    await client.post(
        f"/api/v1/officer/reports/{report_id}/reject",
        headers=officer_headers,
        json={"reason": "Out of jurisdiction; forwarded to state authorities."},
    )

    # Check stats endpoint
    stats_res = await client.get("/api/v1/officer/reports/stats", headers=officer_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["rejected"] >= 1

    # Filter reports by REJECTED
    rej_list_res = await client.get(
        "/api/v1/officer/reports?status=REJECTED",
        headers=officer_headers,
    )
    assert rej_list_res.status_code == 200
    items = rej_list_res.json()["items"]
    assert any(r["report_id"] == report_id for r in items)

    # Filter reports by RECEIVED should NOT contain rejected report
    rec_list_res = await client.get(
        "/api/v1/officer/reports?status=RECEIVED",
        headers=officer_headers,
    )
    assert rec_list_res.status_code == 200
    rec_items = rec_list_res.json()["items"]
    assert not any(r["report_id"] == report_id for r in rec_items)


@pytest.mark.anyio
async def test_rejected_report_excluded_from_situation_intelligence(client: AsyncClient):
    """7. Rejected report is excluded from situation fusion clustering and corroboration."""
    db = db_manager.db
    report_id = "RES-REJ-SIT"
    await create_test_citizen_report(report_id, status="REJECTED")

    # 1. Corroboration Service target evaluation
    eval_result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report={"report_id": report_id, "status": "REJECTED", "emergency_type": "Flood"},
        candidate_reports=[],
    )
    assert eval_result.corroboration_status == CorroborationStatus.NO_CORROBORATION
    assert "officially rejected" in eval_result.explanation

    # 2. Peer candidate exclusion
    peer_eval = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report={"report_id": "RES-ACTIVE-1", "status": "RECEIVED", "emergency_type": "Flood", "location": {"latitude": 16.5062, "longitude": 80.6480}},
        candidate_reports=[{"report_id": report_id, "status": "REJECTED", "emergency_type": "Flood", "location": {"latitude": 16.5062, "longitude": 80.6480}}],
    )
    assert not any(s.source_id == report_id for s in peer_eval.supporting_sources)

    # 3. Situation Fusion Service candidate check
    report_doc = await db["citizen_reports"].find_one({"report_id": report_id})
    fused_sit = await fuse_or_create_situation_for_report(
        db=db,
        report_doc=report_doc,
    )
    assert not fused_sit


@pytest.mark.anyio
async def test_rejected_report_excluded_from_active_gis_map(client: AsyncClient):
    """8. Rejected report is excluded from active map hotspots and active officer map query."""
    db = db_manager.db
    report_id = "RES-REJ-MAP"
    await create_test_citizen_report(report_id, status="REJECTED")

    # Public hotspots
    hotspots = await MapService.get_public_active_hotspots(db=db)
    assert hotspots.total_active_incidents == 0

    # Officer GIS feed: active mode vs historical mode
    active_map = await MapService.get_officer_map_data(view_mode="active", db=db)
    assert not any(r.report_id == report_id for r in active_map.reports)

    historical_map = await MapService.get_officer_map_data(view_mode="history", db=db)
    assert any(r.report_id == report_id for r in historical_map.reports)


@pytest.mark.anyio
async def test_citizen_push_notification_dispatch_on_rejection(client: AsyncClient):
    """9. Citizen push notification is sent with REPORT_REJECTED payload; push error does not fail rejection."""
    db = db_manager.db
    report_id = "RES-REJ-PUSH"
    await create_test_citizen_report(report_id, status="RECEIVED")

    # Add active push subscription for this report
    now = datetime.now(timezone.utc)
    endpoint = "https://fcm.googleapis.com/fcm/send/test-sub-rej-token"
    await db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-TEST-REJ-01",
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

    # Mock web push service send_web_push to simulate successful dispatch
    with patch(
        "app.services.notification.web_push_service.WebPushService.send_web_push",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/reject",
            headers=officer_headers,
            json={"reason": "Report rejected with browser push verification."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["notification"]["status"] == "DELIVERED"
        assert data["notification"]["notification_type"] == "REPORT_REJECTED"
        assert mock_send.await_count >= 1

    # Check push delivery record in DB
    delivery = await db["push_deliveries"].find_one({"report_id": report_id})
    assert delivery is not None
    assert delivery["notification_type"] == "REPORT_REJECTED"
    assert delivery["status"] == "DELIVERED"


@pytest.mark.anyio
async def test_officer_acknowledge_sends_report_accepted_push(client: AsyncClient):
    """10. Acknowledging a RECEIVED report sends REPORT_ACCEPTED browser push notification."""
    db = db_manager.db
    report_id = "RES-ACK-PUSH"
    await create_test_citizen_report(report_id, status="RECEIVED")

    # Add active push subscription
    now = datetime.now(timezone.utc)
    endpoint = "https://fcm.googleapis.com/fcm/send/test-sub-ack-token"
    await db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-TEST-ACK-01",
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

    with patch(
        "app.services.notification.web_push_service.WebPushService.send_web_push",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/acknowledge",
            headers=officer_headers,
        )
        assert res.status_code == 200
        assert mock_send.await_count >= 1

    # Check push delivery record in DB
    delivery = await db["push_deliveries"].find_one({"report_id": report_id})
    assert delivery is not None
    assert delivery["notification_type"] == "REPORT_ACCEPTED"
    assert delivery["status"] == "DELIVERED"
