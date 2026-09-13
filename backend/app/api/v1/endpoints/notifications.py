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
# Twilio WhatsApp Webhook Endpoints
# =======================================================

from app.services.notification.whatsapp_provider import validate_twilio_signature


async def _verify_twilio_request(request: Request, form_dict: Dict[str, str]) -> None:
    """Helper to validate X-Twilio-Signature header on incoming Twilio webhooks."""
    if not settings.TWILIO_VALIDATE_SIGNATURE:
        return

    if not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio signature validation failed: TWILIO_AUTH_TOKEN is not configured on server.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Twilio webhook validation failed: Auth token not configured on server.",
        )

    signature = request.headers.get("X-Twilio-Signature") or request.headers.get("x-twilio-signature")
    if not signature:
        logger.warning("Twilio webhook request rejected: Missing X-Twilio-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Missing X-Twilio-Signature header.",
        )

    url_str = str(request.url)
    is_valid = validate_twilio_signature(
        url=url_str,
        params=form_dict,
        signature=signature,
        auth_token=settings.TWILIO_AUTH_TOKEN,
    )

    # In reverse-proxy setups (e.g., Render/NGINX SSL termination), retry with https://
    if not is_valid and url_str.startswith("http://"):
        https_url = url_str.replace("http://", "https://", 1)
        is_valid = validate_twilio_signature(
            url=https_url,
            params=form_dict,
            signature=signature,
            auth_token=settings.TWILIO_AUTH_TOKEN,
        )

    if not is_valid:
        logger.warning("Twilio webhook rejected: Invalid X-Twilio-Signature for URL %s", url_str)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid Twilio signature.",
        )


@router.post("/whatsapp/twilio/status", summary="Twilio WhatsApp Delivery Status Callback")
@router.post("/sms/twilio/status", summary="Twilio SMS Delivery Status Callback")
@router.post("/twilio/status", summary="Twilio Unified Messaging Delivery Status Callback")
async def receive_twilio_status(
    request: Request,
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, Any]:
    """
    Twilio Delivery Status Callback Endpoint (WhatsApp & SMS).
    Accepts Twilio delivery states (queued, accepted, sending, sent, delivered, undelivered, read, failed)
    and updates MongoDB notification_deliveries idempotently.
    Validates X-Twilio-Signature in production.
    """
    try:
        form = await request.form()
        form_dict = {k: str(v) for k, v in form.items()}
    except Exception as ex:
        logger.warning("Failed to parse Twilio status callback form body: %s", str(ex))
        form_dict = {}

    await _verify_twilio_request(request, form_dict)

    try:
        result = await service.process_twilio_status_callback(form_dict)
        return {"status": "ok", "result": result}
    except Exception as ex:
        logger.error("Error processing Twilio status callback: %s", str(ex), exc_info=True)
        return {"status": "error", "detail": str(ex)}


@router.post("/whatsapp/twilio/inbound", summary="Twilio WhatsApp Inbound Message Acknowledgment")
async def receive_twilio_whatsapp_inbound(
    request: Request,
    service: NotificationService = Depends(get_notification_service),
) -> PlainTextResponse:
    """
    Twilio WhatsApp Inbound Message Receiver.
    Acknowledges incoming messages safely with TwiML Response.
    IMPORTANT: Inbound WhatsApp messages NEVER trigger citizen emergency reporting.
    Citizen emergency reporting remains strictly on /report-emergency.
    """
    try:
        form = await request.form()
        form_dict = {k: str(v) for k, v in form.items()}
    except Exception as ex:
        logger.warning("Failed to parse Twilio inbound form body: %s", str(ex))
        form_dict = {}

    await _verify_twilio_request(request, form_dict)

    await service.process_twilio_inbound(form_dict)

    # Return valid empty TwiML response
    twiml_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return PlainTextResponse(content=twiml_response, media_type="application/xml", status_code=status.HTTP_200_OK)


@router.post("/sms/twilio/inbound", summary="Twilio SMS Inbound Message Acknowledgment")
@router.post("/twilio/inbound", summary="Twilio Inbound Message Receiver")
async def receive_twilio_sms_inbound(
    request: Request,
    service: NotificationService = Depends(get_notification_service),
) -> PlainTextResponse:
    """
    Twilio SMS Inbound Message Receiver.
    Acknowledges incoming messages safely with TwiML Response.
    IMPORTANT: Inbound SMS messages NEVER trigger citizen emergency reporting.
    Citizen emergency reporting remains strictly on /report-emergency.
    """
    try:
        form = await request.form()
        form_dict = {k: str(v) for k, v in form.items()}
    except Exception as ex:
        logger.warning("Failed to parse Twilio SMS inbound form body: %s", str(ex))
        form_dict = {}

    await _verify_twilio_request(request, form_dict)

    await service.process_twilio_inbound_sms(form_dict)

    # Return valid empty TwiML response
    twiml_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return PlainTextResponse(content=twiml_response, media_type="application/xml", status_code=status.HTTP_200_OK)


# =======================================================
# User-Scoped Notification Endpoints
# =======================================================

@router.get("", response_model=List[NotificationUserView], summary="Get User Notifications")
@router.get("/", response_model=List[NotificationUserView], include_in_schema=False)
async def list_notifications(
    category: Optional[NotificationCategory] = Query(None, description="Filter by notification category"),
    severity: Optional[NotificationSeverity] = Query(None, description="Filter by notification severity"),
    unread_only: bool = Query(False, description="Filter to unread notifications only"),
    limit: int = Query(50, ge=1, le=200, description="Max notifications to return"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> List[NotificationUserView]:
    """
    Fetch notifications scoped to the authenticated user from authoritative MongoDB state.
    Supports optional category, severity, unread filtering, and pagination.
    """
    return await service.get_user_notifications(
        user_id=current_user.id,
        category=category,
        severity=severity,
        unread_only=unread_only,
        limit=limit,
        skip=skip,
    )


@router.get("/unread-count", summary="Get Unread Notification Count")
async def get_unread_count(
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, int]:
    """
    Fetch real unread in-app notification count for the authenticated user from authoritative MongoDB state.
    """
    count = await service.get_unread_count(user_id=current_user.id)
    return {"count": count, "unread_count": count}


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
