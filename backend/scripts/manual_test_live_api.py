import httpx
import asyncio
import json

async def run_live_manual_test():
    base_url = "http://127.0.0.1:8000/api/v1"
    
    print("=" * 70)
    print("STEP 10 — LIVE RUNTIME VERIFICATION (Dipesh Kumar Officer Session)")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # 1. Login as Emergency Officer Dipesh Kumar
        print("\n[STEP 1] Logging in as Emergency Officer 9999999002...")
        login_res = await client.post("/auth/login", json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_data = login_res.json()
        token = auth_data["access_token"]
        user = auth_data["user"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  [SUCCESS] Authenticated User: '{user['full_name']}' (ID: {user['id']}, Role: {user['role']}, Phone: {user['phone']})")
        assert user["full_name"] == "Dipesh Kumar", f"Expected Dipesh Kumar, got {user['full_name']}"

        # 2. View Report RES-ENFC4NT3
        print("\n[STEP 2] Opening report RES-ENFC4NT3...")
        view_res = await client.get("/officer/reports/RES-ENFC4NT3", headers=headers)
        assert view_res.status_code == 200, f"Get report failed: {view_res.text}"
        report = view_res.json()
        print(f"  [SUCCESS] Report Retrieved: ID={report['report_id']}, Status={report['status']}, Priority={report['priority']}")
        print(f"  Acknowledged By: {report['acknowledged_by']}")

        # 3. Add Operational Note
        print("\n[STEP 3] Adding operational note as Dipesh Kumar...")
        note_text = "Field unit Alpha arriving at Old Town for immediate assessment."
        note_res = await client.post("/officer/reports/RES-ENFC4NT3/notes", json={"note": note_text}, headers=headers)
        assert note_res.status_code == 200, f"Add note failed: {note_res.text}"
        updated_notes = note_res.json()["notes"]
        last_note = updated_notes[-1]
        print(f"  [SUCCESS] Note Added by '{last_note['author_name']}' ({last_note['author_role']}): '{last_note['note']}' at {last_note['created_at']}")
        assert last_note["author_name"] == "Dipesh Kumar"

        # 4. Change Priority to CRITICAL
        print("\n[STEP 4] Updating priority to CRITICAL...")
        prio_res = await client.patch("/officer/reports/RES-ENFC4NT3/priority", json={"priority": "CRITICAL"}, headers=headers)
        assert prio_res.status_code == 200, f"Priority update failed: {prio_res.text}"
        print(f"  [SUCCESS] New Priority: {prio_res.json()['priority']}")

        # 5. Update Status to UNDER_ASSESSMENT
        print("\n[STEP 5] Transitioning status to UNDER_ASSESSMENT...")
        status_res = await client.patch("/officer/reports/RES-ENFC4NT3/status", json={
            "status": "UNDER_ASSESSMENT",
            "reason": "Field unit on scene initiating rescue assessment"
        }, headers=headers)
        assert status_res.status_code == 200, f"Status update failed: {status_res.text}"
        print(f"  [SUCCESS] New Status: {status_res.json()['status']}")

        # 6. Retrieve Final Timeline
        print("\n[STEP 6] Inspecting complete operational audit timeline...")
        timeline_res = await client.get("/officer/reports/RES-ENFC4NT3/timeline", headers=headers)
        assert timeline_res.status_code == 200, f"Timeline fetch failed: {timeline_res.text}"
        timeline = timeline_res.json()
        print(f"  Total Timeline Events: {len(timeline)}")

        for idx, ev in enumerate(timeline):
            print(f"    [{idx}] {ev['event_type']} | Actor: '{ev.get('actor_name')}' ({ev.get('actor_role')}) | Details: {ev['details']} | Timestamp: {ev['timestamp']}")
            assert "Marcus Vance" not in str(ev), f"Found Marcus Vance in event: {ev}"
            if ev.get("actor_id") == user["id"]:
                assert ev.get("actor_name") == "Dipesh Kumar", f"Expected Dipesh Kumar actor name, got: {ev.get('actor_name')}"

        # 7. Test rapid reload deduplication
        print("\n[STEP 7] Rapid reload deduplication check (5 calls)...")
        for _ in range(5):
            r = await client.get("/officer/reports/RES-ENFC4NT3", headers=headers)
            assert r.status_code == 200

        timeline_after_reload = (await client.get("/officer/reports/RES-ENFC4NT3/timeline", headers=headers)).json()
        assert len(timeline_after_reload) == len(timeline), f"Duplicate events created on reload! Before: {len(timeline)}, After: {len(timeline_after_reload)}"
        print(f"  [SUCCESS] Timeline length remained strictly {len(timeline_after_reload)} (Zero duplicates created).")

    print("\n" + "=" * 70)
    print("ALL LIVE RUNTIME VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_live_manual_test())
