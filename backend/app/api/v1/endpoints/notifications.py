import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.enums import NotificationCategory, NotificationSeverity
from app.models.notification import (
    NotificationPreference,
    NotificationPreferenceUpdate,
    NotificationUserView,
)
from app.models.user import UserResponse
from app.services.notification.notification_service import (
    NotificationService,
    get_notification_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =======================================================
# Meta WhatsApp Cloud API Webhook Endpoints (Public/Meta)
# =======================================================

@router.get("/whatsapp/webhook", response_class=PlainTextResponse, summary="Meta WhatsApp Webhook Verification")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode", description="Meta verification mode ('subscribe')"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token", description="Configured verification secret token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge", description="Challenge string echoed back on success"),
) -> PlainTextResponse:
    """
    Meta WhatsApp Cloud API Webhook Verification Endpoint.
    Validates hub.mode == 'subscribe' and hub.verify_token matches configured backend secret.
    Returns hub.challenge as plain text on success, otherwise HTTP 403 Forbidden.
    """
    configured_token = settings.whatsapp_verify_token
    if not configured_token:
        logger.warning("WhatsApp webhook verification rejected: WHATSAPP_VERIFY_TOKEN is not configured on the backend.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook verification failed: Verify token not configured on server.",
        )

    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == configured_token:
        logger.info("Meta WhatsApp webhook verified successfully.")
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    logger.warning(
        "WhatsApp webhook verification failed. mode=%s token_valid=%s",
        hub_mode,
        bool(hub_verify_token and hub_verify_token == configured_token),
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification failed: Invalid mode or verify token.",
    )


@router.post("/whatsapp/webhook", summary="Meta WhatsApp Webhook Event Ingestion")
async def receive_whatsapp_webhook(
    request: Request,
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, Any]:
    """
    Meta WhatsApp Cloud API Webhook Event Receiver.
    Accepts genuine Meta Cloud API delivery updates (sent, delivered, read, failed)
    and processes events idempotently. Always returns HTTP 200 to acknowledge receipt to Meta.
    """
    try:
        payload = await request.json()
    except Exception as ex:
        logger.warning("WhatsApp webhook received malformed non-JSON payload: %s", str(ex))
        return {"status": "ignored", "reason": "malformed_json"}

    try:
        result = await service.process_whatsapp_webhook(payload)
        return {"status": "ok", "message": "EVENT_RECEIVED", "details": result}
    except Exception as ex:
        logger.error("Error processing WhatsApp webhook payload: %s", str(ex), exc_info=True)
        return {"status": "ok", "message": "EVENT_RECEIVED", "error": "processing_error"}


# =======================================================
# User-Scoped Notification Endpoints
# =======================================================

@router.get("/channels/status", summary="Get Notification Channels Status")
async def get_channel_status(
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, Any]:
    """
    Return operational and configuration status for In-App and WhatsApp channels.
    Never exposes provider tokens or credentials.
    """
    return service.get_channel_status()


@router.get("/preferences", response_model=NotificationPreference)
async def get_notification_preferences(
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreference:
    """
    Retrieve notification preferences for the authenticated user.
    """
    return await service.get_user_preferences(user_id=current_user.id)


@router.put("/preferences", response_model=NotificationPreference)
async def update_notification_preferences(
    update_data: NotificationPreferenceUpdate,
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreference:
    """
    Update notification preferences for the authenticated user.
    """
    return await service.update_user_preferences(user_id=current_user.id, update=update_data)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, Any]:
    """
    Mark a single notification as read for the authenticated user (IDOR protected).
    """
    success = await service.mark_as_read(user_id=current_user.id, notification_id=notification_id)
    if not success:
        # Check if notification exists at all
        notifs = await service.get_user_notifications(user_id=current_user.id, limit=5)
        matched = any(n.notification_id == notification_id for n in notifs)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied.",
            )
    return {"success": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, Any]:
    """
    Mark all unread in-app notifications as read for current user.
    """
    count = await service.mark_all_as_read(user_id=current_user.id)
    return {"success": True, "count": count}


@router.get("/{notification_id}", response_model=NotificationUserView)
async def get_notification_by_id(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationUserView:
    """
    Retrieve a single notification's user view.
    """
    notifs = await service.get_user_notifications(user_id=current_user.id, limit=200)
    for n in notifs:
        if n.notification_id == notification_id:
            return n
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Notification not found or access denied.",
    )
