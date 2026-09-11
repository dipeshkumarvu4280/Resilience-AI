import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
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


@router.get("", response_model=List[NotificationUserView])
async def list_notifications(
    category: Optional[NotificationCategory] = Query(None, description="Filter by category"),
    severity: Optional[NotificationSeverity] = Query(None, description="Filter by severity"),
    unread_only: bool = Query(False, description="Filter unread notifications only"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> List[NotificationUserView]:
    """
    Fetch paginated, user-scoped notifications for the authenticated operator/citizen.
    Strictly isolated: users cannot view another user's notifications.
    """
    return await service.get_user_notifications(
        user_id=current_user.id,
        category=category,
        severity=severity,
        unread_only=unread_only,
        limit=limit,
        skip=skip,
    )


@router.get("/unread-count")
async def get_unread_count(
    current_user: UserResponse = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Dict[str, int]:
    """
    Return exact unread in-app notification count for current user.
    """
    count = await service.get_unread_count(user_id=current_user.id)
    return {"unread_count": count}


@router.get("/channels/status")
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
