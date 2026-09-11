import asyncio
import os
import sys
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.db.mongodb import connect_to_mongo, get_database


async def run_real_endpoint_test():
    print("=" * 70)
    print("REAL RUNTIME BROWSER ENDPOINT VERIFICATION (GEMINI 429 -> OPENAI FALLBACK)")
    print("=" * 70)

    await connect_to_mongo()
    db = get_database()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1", timeout=60.0) as client:
        # 1. Login as Emergency Officer Dipesh Kumar
        print("\n[STEP 1] Authenticating as Emergency Officer 9999999002...")
        login_res = await client.post("/auth/login", json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  [SUCCESS] Authenticated token acquired.")

        # 2. Get the real report from MongoDB
        real_report = await db["citizen_reports"].find_one({"report_id": "RES-A6KAGDSA"}) or await db["citizen_reports"].find_one({}, sort=[("created_at", -1)])
        report_id = real_report["report_id"]
        print(f"\n[FOUND REAL TARGET REPORT]: {report_id}")
        print(f"  Emergency Type: {real_report.get('emergency_type')}")
        print(f"  Description: '{real_report.get('description')}'")
        print(f"  Initial Status in DB: {real_report.get('llm_extraction', {}).get('status') if real_report.get('llm_extraction') else 'None'}")

        # 3. Call GET /officer/reports/{report_id} (Exact endpoint browser calls when viewing modal)
        print(f"\n[STEP 2] Calling GET /officer/reports/{report_id} (Browser detail endpoint)...")
        get_res = await client.get(f"/officer/reports/{report_id}", headers=headers)
        assert get_res.status_code == 200, f"GET report details failed: {get_res.text}"

        detail = get_res.json()
        llm = detail.get("llm_extraction")

        print("\n[STEP 3] Evaluating Auto-Refreshed AI Extraction Result:")
        assert llm is not None, "LLM Extraction should not be None"
        print(f"  - Status: {llm.get('status')}")
        print(f"  - Provider: {llm.get('provider')}")
        print(f"  - Fallback Used: {llm.get('fallback_used')}")
        print(f"  - Primary Provider: {llm.get('primary_provider')}")
        print(f"  - Primary Provider Error: {llm.get('primary_provider_error')}")
        print(f"  - Model: {llm.get('model')}")
        print(f"  - Overall Confidence: {llm.get('overall_confidence')}")
        if llm.get("hazard"):
            print(f"  - Hazard: {llm['hazard'].get('value')} (Confidence: {llm['hazard'].get('confidence')})")
        if llm.get("affected_population"):
            print(f"  - Affected Population: {llm['affected_population'].get('estimated_count')}")
        print(f"  - Vulnerable Groups: {[g.get('group_type') for g in llm.get('vulnerable_groups', [])]}")
        print(f"  - Reported Needs: {[n.get('need_type') for n in llm.get('reported_needs', [])]}")

        # 4. Trigger explicit POST /officer/reports/{report_id}/extract-text-evidence
        print(f"\n[STEP 4] Calling POST /officer/reports/{report_id}/extract-text-evidence (Explicit re-extract endpoint)...")
        post_res = await client.post(f"/officer/reports/{report_id}/extract-text-evidence", headers=headers)
        assert post_res.status_code == 200, f"POST extract-text-evidence failed: {post_res.text}"

        post_detail = post_res.json()
        post_llm = post_detail.get("llm_extraction")
        print(f"  [SUCCESS] Explicit extraction returned:")
        print(f"  - Status: {post_llm.get('status')}")
        print(f"  - Provider: {post_llm.get('provider')}")
        print(f"  - Fallback Used: {post_llm.get('fallback_used')}")
        print(f"  - Primary Provider: {post_llm.get('primary_provider')}")
        print(f"  - Model: {post_llm.get('model')}")

        assert post_llm.get("status") == "SUCCESS", f"Expected SUCCESS, got {post_llm.get('status')}"
        assert post_llm.get("provider") == "OPENAI", f"Expected OPENAI, got {post_llm.get('provider')}"
        assert post_llm.get("fallback_used") is True, f"Expected fallback_used=True, got {post_llm.get('fallback_used')}"

    print("\n" + "=" * 70)
    print("REAL RUNTIME BROWSER ENDPOINT VERIFICATION: PASS!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_real_endpoint_test())
