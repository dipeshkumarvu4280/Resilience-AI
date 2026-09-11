from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)


class InAppDeliveryState(BaseModel):
    status: NotificationDeliveryStatus = NotificationDeliveryStatus.PENDING
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None


class WhatsAppDeliveryState(BaseModel):
    status: NotificationDeliveryStatus = NotificationDeliveryStatus.NOT_CONFIGURED
    queued_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class NotificationRecipientInfo(BaseModel):
    user_id: str
    role: Optional[UserRole] = None
    phone_number: Optional[str] = None
    in_app: InAppDeliveryState = Field(default_factory=InAppDeliveryState)
    whatsapp: WhatsAppDeliveryState = Field(default_factory=WhatsAppDeliveryState)


class NotificationDeepLink(BaseModel):
    entity_type: Optional[str] = None  # e.g., "CITIZEN_REPORT", "SITUATION", "COORDINATION_PLAN", "MONITORING_EVENT"
    entity_id: Optional[str] = None
    situation_id: Optional[str] = None
    coordination_plan_id: Optional[str] = None
    view_hint: Optional[str] = None  # e.g., "reports", "situations", "monitoring", "plans"


class Notification(BaseModel):
    notification_id: str
    event_id: Optional[str] = None
    category: NotificationCategory
    event_type: str
    severity: NotificationSeverity = NotificationSeverity.LOW
    title: str
    message: str
    deep_link: Optional[NotificationDeepLink] = None
    is_simulation: bool = False
    fingerprint: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recipients: List[NotificationRecipientInfo] = Field(default_factory=list)


class NotificationPreference(BaseModel):
    preference_id: str
    user_id: str
    in_app_enabled: bool = True
    whatsapp_enabled: bool = False
    phone_number: Optional[str] = None
    notify_critical: bool = True
    notify_high: bool = True
    notify_operational: bool = True
    notify_plan_updates: bool = True
    notify_monitoring: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    phone_number: Optional[str] = None
    notify_critical: Optional[bool] = None
    notify_high: Optional[bool] = None
    notify_operational: Optional[bool] = None
    notify_plan_updates: Optional[bool] = None
    notify_monitoring: Optional[bool] = None


class NotificationUserView(BaseModel):
    """User-scoped representation of a notification"""
    notification_id: str
    event_id: Optional[str] = None
    category: NotificationCategory
    event_type: str
    severity: NotificationSeverity
    title: str
    message: str
    deep_link: Optional[NotificationDeepLink] = None
    is_simulation: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    in_app_status: NotificationDeliveryStatus
    read_at: Optional[datetime] = None
    whatsapp_status: NotificationDeliveryStatus
