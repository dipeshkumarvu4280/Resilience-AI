import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.models.enums import UserRole, GuidanceApprovalState
from app.models.safety_guidance import (
    PushSubscriptionCreate,
    PushUnsubscribeRequest,
    CitizenSafetyGuidanceResponse,
    SafetyGuidanceReviewRequest,
)
from app.services.notification.web_push_service import WebPushService
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
from app.api.deps import get_current_user

logger = logging.getLogger("resilience.api.safety_guidance")

router = APIRouter()


# ==============================================================================
# 1. WEB PUSH VAPID & SUBSCRIPTION ENDPOINTS (CITIZEN ACCESS)
# ==============================================================================

@router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """
    Returns the application VAPID public key formatted for browser Web Push subscription.
    """
    public_key = WebPushService.get_public_vapid_key()
    return {
        "success": True,
        "vapid_public_key": public_key,
        "algorithm": "ECDSA_P256",
        "format": "RAW_P256_BASE64URL",
    }


@router.get("/push/status")
async def get_citizen_push_status(
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Read-only diagnostic endpoint reporting truthful Web Push subsystem status.
    Never exposes VAPID private keys, auth secrets, or credentials.
    """
    return await WebPushService.get_diagnostic_status(db=db)


@router.post("/push/subscribe")
async def subscribe_web_push(
    sub_in: PushSubscriptionCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Idempotently registers or updates a browser Web Push subscription with NIST P-256 keys.
    """
    try:
        record = await WebPushService.save_subscription(sub_in, db=db)
        
        # If subscription is associated with a report that has active guidance, auto-dispatch initial guidance alert
        if sub_in.report_id:
            guidance_doc = await db["citizen_safety_guidance"].find_one({
                "report_id": sub_in.report_id,
                "status": "ACTIVE",
            })
            if guidance_doc:
                try:
                    from app.models.safety_guidance import CitizenSafetyGuidance
                    from app.models.enums import SafetyNotificationType
                    guidance_obj = CitizenSafetyGuidance(**guidance_doc)
                    await WebPushService.notify_citizen_guidance_update(
                        guidance_obj,
                        notification_type=SafetyNotificationType.SAFETY_GUIDANCE_READY,
                        db=db,
                    )
                except Exception as auto_push_err:
                    logger.info(f"Initial guidance auto-dispatch notice: {auto_push_err}")

        return {
            "success": True,
            "subscription_id": record.subscription_id,
            "status": record.status.value,
            "message": "Emergency alert subscription active.",
        }
    except Exception as e:
        logger.error(f"Error registering web push subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register push subscription.",
        )


@router.delete("/push/subscribe")
async def unsubscribe_web_push(
    unsub_req: Optional[PushUnsubscribeRequest] = None,
    endpoint: Optional[str] = Query(None, description="Browser push subscription endpoint to remove"),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Unsubscribes a browser endpoint from Web Push emergency alerts.
    """
    target_endpoint = endpoint or (unsub_req.endpoint if unsub_req else None)
    if not target_endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'endpoint' in query parameter or request body.",
        )

    success = await WebPushService.remove_subscription(target_endpoint, db=db)
    return {
        "success": success,
        "message": "Push subscription removed." if success else "Subscription not found.",
    }


@router.post("/push/test")
async def send_test_web_push(
    report_id: Optional[str] = Query(None, description="Optional report ID to target"),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Diagnostic endpoint to dispatch a genuine RFC 8291 Web Push alert to registered browser subscriptions.
    """
    query: Dict[str, Any] = {"status": "ACTIVE"}
    if report_id:
        query["report_ids"] = report_id

    cursor = db["push_subscriptions"].find(query)
    subscriptions = await cursor.to_list(20)
    if not subscriptions:
        return {
            "success": False,
            "request_status": "no_subscriptions_for_target",
            "subscriptions_found": 0,
            "total_targets": 0,
            "sent_count": 0,
            "web_push_attempted": False,
            "provider_status": None,
            "delivery_status": "NO_SUBSCRIPTIONS",
            "message": f"No active push subscriptions found{' for report ' + report_id if report_id else ''}.",
            "failed_details": [],
        }

    from app.models.safety_guidance import PushNotificationPayload
    payload = PushNotificationPayload(
        title="🚨 RESILIENCE Emergency Alert",
        body="Live emergency alert channel is verified and active on this device.",
        url=f"/safety-guidance/{report_id}" if report_id else "/citizen/report",
        tag=f"alert-{int(datetime.now(timezone.utc).timestamp())}",
    )

    sent = 0
    failed_details = []
    last_provider_status = None
    for doc in subscriptions:
        record = WebPushService._doc_to_record(doc)
        ok = await WebPushService.send_web_push(record, payload, db=db)
        updated_sub = await db["push_subscriptions"].find_one({"subscription_id": record.subscription_id})
        last_provider_status = (updated_sub or {}).get("last_provider_status")
        if ok:
            sent += 1
        else:
            failed_details.append({
                "subscription_id": record.subscription_id,
                "provider_status": last_provider_status,
                "reason": (updated_sub or {}).get("failure_reason") or "Delivery rejected or expired",
            })

    is_success = (sent > 0)
    delivery_status = "ACCEPTED_201" if is_success else "FAILED"
    msg = (
        f"Dispatched {sent}/{len(subscriptions)} real Web Push notifications."
        if is_success
        else f"Delivery failed — 0 of {len(subscriptions)} subscriptions accepted by push service."
    )

    return {
        "success": is_success,
        "request_status": "accepted" if is_success else "failed",
        "subscriptions_found": len(subscriptions),
        "total_targets": len(subscriptions),
        "sent_count": sent,
        "web_push_attempted": True,
        "provider_status": last_provider_status or ("ACCEPTED_201" if is_success else "PROVIDER_ERROR"),
        "delivery_status": delivery_status,
        "message": msg,
        "failed_details": failed_details,
    }


# ==============================================================================
# 2. CITIZEN SAFETY GUIDANCE RETRIEVAL (SECURE ACCESS TOKEN & REPORT ID)
# ==============================================================================

@router.get("/safety-guidance/{secure_token}/history")
async def get_safety_guidance_history(
    secure_token: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Retrieves the full immutable audit version trail for a safety guidance token.
    """
    doc = await db["citizen_safety_guidance"].find_one({
        "$or": [
            {"secure_access_token": secure_token},
            {"guidance_id": secure_token},
        ]
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Safety guidance not found.",
        )

    report_id = doc.get("report_id")
    all_versions_cursor = db["citizen_safety_guidance"].find({"report_id": report_id}).sort("version", 1)
    
    versions = []
    async for v_doc in all_versions_cursor:
        g = SafetyGuidanceAgent._doc_to_guidance(v_doc)
        versions.append({
            "guidance_id": g.guidance_id,
            "version": g.version,
            "status": g.status,
            "approval_state": g.approval_state.value,
            "generated_at": g.generated_at,
            "valid_until": g.valid_until,
            "change_reason": g.change_reason,
            "trigger_event_id": g.trigger_event_id,
            "destination_name": g.recommended_destination.destination_name if g.recommended_destination else None,
            "route_status": g.route.route_status.value if g.route else "NONE",
            "is_stale": g.is_stale,
        })

    return {
        "success": True,
        "report_id": report_id,
        "total_versions": len(versions),
        "versions": versions,
    }


@router.get("/safety-guidance/{secure_token}", response_model=CitizenSafetyGuidanceResponse)
async def get_safety_guidance_by_token(
    secure_token: str,
    lang: Optional[str] = Query(None, description="Optional language code override for guidance actions and precautions"),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Retrieves Citizen Safety Guidance using a high-entropy secure access token.
    If the requested token corresponds to a superseded historical version,
    automatically returns the latest active version with pointer.
    """
    doc = await db["citizen_safety_guidance"].find_one({
        "$or": [
            {"secure_access_token": secure_token},
            {"guidance_id": secure_token},
        ]
    })
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Safety guidance not found or access token expired.",
        )

    # Check if superseded
    if doc.get("status") == "SUPERSEDED" and doc.get("report_id"):
        latest_doc = await db["citizen_safety_guidance"].find_one({
            "report_id": doc["report_id"],
            "status": "ACTIVE",
        })
        if latest_doc:
            latest_guidance = SafetyGuidanceAgent._doc_to_guidance(latest_doc)
            if lang:
                latest_guidance = SafetyGuidanceAgent.localize_guidance(latest_guidance, lang)
            return CitizenSafetyGuidanceResponse(
                success=True,
                guidance=latest_guidance,
                secure_access_token=latest_guidance.secure_access_token,
                latest_active_token=latest_guidance.secure_access_token,
                message=f"Displaying latest active guidance (Version {latest_guidance.version}). Previous version was superseded.",
            )

    guidance = SafetyGuidanceAgent._doc_to_guidance(doc)
    if lang:
        guidance = SafetyGuidanceAgent.localize_guidance(guidance, lang)
    return CitizenSafetyGuidanceResponse(
        success=True,
        guidance=guidance,
        secure_access_token=secure_token,
        latest_active_token=guidance.secure_access_token,
        message="Safety guidance retrieved successfully.",
    )


@router.get("/reports/{report_id}/safety-guidance", response_model=CitizenSafetyGuidanceResponse)
async def get_safety_guidance_for_report(
    report_id: str,
    lang: Optional[str] = Query(None, description="Optional language code override for guidance actions and precautions"),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Generates or retrieves structured Safety Guidance for a specific report ID.
    """
    try:
        guidance = await SafetyGuidanceAgent.generate_safety_guidance(
            report_id=report_id,
            db=db,
            force_refresh=False,
        )
        if lang:
            guidance = SafetyGuidanceAgent.localize_guidance(guidance, lang)
        return CitizenSafetyGuidanceResponse(
            success=True,
            guidance=guidance,
            secure_access_token=guidance.secure_access_token,
            message="Safety guidance retrieved successfully.",
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error fetching safety guidance for report {report_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to synthesize safety guidance.")


@router.post("/reports/{report_id}/safety-guidance/refresh", response_model=CitizenSafetyGuidanceResponse)
async def refresh_safety_guidance_for_report(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Force-refreshes safety guidance with the latest real-time operational context.
    """
    try:
        guidance = await SafetyGuidanceAgent.generate_safety_guidance(
            report_id=report_id,
            db=db,
            force_refresh=True,
        )
        return CitizenSafetyGuidanceResponse(
            success=True,
            guidance=guidance,
            secure_access_token=guidance.secure_access_token,
            message="Safety guidance refreshed successfully with latest operational data.",
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error refreshing safety guidance for report {report_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to refresh safety guidance.")


# ==============================================================================
# 3. OFFICER HITL REVIEW & APPROVAL ENDPOINT
# ==============================================================================

@router.post("/officer/safety-guidance/{guidance_id}/review")
async def review_safety_guidance(
    guidance_id: str,
    review_req: SafetyGuidanceReviewRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Emergency Officer HITL Review & Approval workflow.
    Approves, modifies, or rejects high-risk safety guidance before or after citizen delivery.
    """
    # Verify officer role
    user_role = getattr(current_user, "role", "")
    if user_role not in [UserRole.EMERGENCY_OFFICER.value, UserRole.ADMIN.value, "EMERGENCY_OFFICER", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only authorized Emergency Officers or Administrators may review safety guidance.",
        )

    doc = await db["citizen_safety_guidance"].find_one({"guidance_id": guidance_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safety guidance {guidance_id} not found.",
        )

    action_upper = review_req.action.upper()
    now_utc = datetime.now(timezone.utc)
    officer_name = getattr(current_user, "full_name", "Emergency Officer")

    update_fields: Dict[str, Any] = {
        "reviewed_by": officer_name,
        "reviewed_at": now_utc,
        "officer_review_notes": review_req.officer_notes,
    }

    if action_upper in ["APPROVE", "APPROVED"]:
        update_fields["approval_state"] = GuidanceApprovalState.APPROVED.value
    elif action_upper in ["MODIFY", "MODIFIED"]:
        update_fields["approval_state"] = GuidanceApprovalState.MODIFIED.value
        if review_req.modified_actions:
            update_fields["immediate_actions"] = review_req.modified_actions
        if review_req.modified_precautions:
            update_fields["precautions"] = review_req.modified_precautions
    elif action_upper in ["REJECT", "REJECTED"]:
        update_fields["approval_state"] = GuidanceApprovalState.REJECTED.value
        update_fields["status"] = "REJECTED_BY_OFFICER"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review action. Must be APPROVE/APPROVED, MODIFY/MODIFIED, or REJECT/REJECTED.",
        )

    await db["citizen_safety_guidance"].update_one(
        {"guidance_id": guidance_id},
        {"$set": update_fields},
    )

    updated_doc = await db["citizen_safety_guidance"].find_one({"guidance_id": guidance_id})
    guidance = SafetyGuidanceAgent._doc_to_guidance(updated_doc)

    # If approved or modified, trigger push notification update to citizen
    if action_upper in ["APPROVE", "MODIFY"]:
        try:
            await WebPushService.notify_citizen_guidance_update(guidance, db=db)
        except Exception as ex:
            logger.warning(f"Push notification error on officer review: {ex}")

    return {
        "success": True,
        "guidance_id": guidance_id,
        "approval_state": guidance.approval_state.value,
        "message": f"Safety guidance {action_upper.lower()}d successfully by {officer_name}.",
        "guidance": guidance,
    }
