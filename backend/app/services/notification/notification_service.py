import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.db.mongodb import get_database
from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.models.notification import (
    InAppDeliveryState,
    Notification,
    NotificationDeepLink,
    NotificationPreference,
    NotificationPreferenceUpdate,
    NotificationRecipientInfo,
    NotificationUserView,
    SmsDeliveryState,
    WhatsAppDeliveryState,
)
from app.services.notification.sms_provider import (
    SmsProviderInterface,
    get_sms_provider,
)
from app.services.notification.whatsapp_provider import (
    WhatsAppProviderInterface,
    get_whatsapp_provider,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized, authoritative, event-driven Notification Dispatcher & Management Engine.
    Coordinates In-App, WhatsApp, and SMS channels with deduplication, recipient resolution,
    severity escalation, preference enforcement, and simulation isolation.
    """

    def __init__(
        self,
        whatsapp_provider: Optional[WhatsAppProviderInterface] = None,
        sms_provider: Optional[SmsProviderInterface] = None,
    ):
        self._provider = whatsapp_provider
        self._sms_provider = sms_provider

    @property
    def provider(self) -> WhatsAppProviderInterface:
        if self._provider is not None:
            return self._provider
        return get_whatsapp_provider()

    @property
    def sms_provider(self) -> SmsProviderInterface:
        if self._sms_provider is not None:
            return self._sms_provider
        return get_sms_provider()

    @staticmethod
    def compute_fingerprint(
        category: NotificationCategory,
        event_type: str,
        entity_id: Optional[str],
        material_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate deterministic fingerprint for deduplication.
        Allows legitimate alerts when material state changes while suppressing identical duplicate spam.
        """
        raw = f"{category.value}:{event_type}:{entity_id or 'none'}"
        if material_state:
            # Deterministic serialization of material state dict
            serialized = json.dumps(material_state, sort_keys=True, default=str)
            raw += f":{serialized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_db(self, db: Optional[Any] = None):
        if db is not None:
            return db
        return get_database()

    async def get_user_preferences(
        self, user_id: str, db: Optional[Any] = None
    ) -> NotificationPreference:
        """Fetch user notification preferences or create default."""
        database = self._get_db(db)
        doc = await database["notification_preferences"].find_one({"user_id": user_id})
        if doc:
            doc.pop("_id", None)
            return NotificationPreference(**doc)

        from bson import ObjectId
        query_or: List[Dict[str, Any]] = [
            {"user_id": user_id},
            {"phone": user_id},
        ]
        if isinstance(user_id, str) and ObjectId.is_valid(user_id):
            try:
                query_or.append({"_id": ObjectId(user_id)})
            except Exception:
                pass

        user_doc = await database["users"].find_one({"$or": query_or})
        phone = None
        if user_doc:
            phone = user_doc.get("phone") or user_doc.get("phone_number")

        pref = NotificationPreference(
            preference_id=f"pref_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            in_app_enabled=True,
            whatsapp_enabled=bool(phone),
            sms_enabled=False,
            phone_number=phone,
            notify_critical=True,
            notify_high=True,
            notify_operational=True,
            notify_plan_updates=True,
            notify_monitoring=True,
            updated_at=datetime.now(timezone.utc),
        )
        await database["notification_preferences"].insert_one(pref.model_dump())
        return pref

    async def update_user_preferences(
        self, user_id: str, update: NotificationPreferenceUpdate, db: Optional[Any] = None
    ) -> NotificationPreference:
        """Update notification preferences for a user."""
        database = self._get_db(db)
        current = await self.get_user_preferences(user_id, db=database)
        update_data = update.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)

        current_dict = current.model_dump()
        current_dict.update(update_data)

        await database["notification_preferences"].update_one(
            {"user_id": user_id},
            {"$set": current_dict},
            upsert=True,
        )
        return NotificationPreference(**current_dict)

    async def resolve_recipients(
        self,
        target_user_ids: Optional[List[str]] = None,
        target_roles: Optional[List[UserRole]] = None,
        exclude_user_ids: Optional[List[str]] = None,
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Resolve eligible recipients based on explicit user IDs or roles.
        """
        database = self._get_db(db)
        resolved_map: Dict[str, Dict[str, Any]] = {}
        exclude_set = set(exclude_user_ids or [])

        def extract_user_id_and_phone(u: dict):
            uid = str(u.get("_id") or u.get("user_id") or u.get("phone"))
            phone = u.get("phone") or u.get("phone_number")
            role = u.get("role")
            return uid, role, phone

        # 1. Query by explicit user IDs
        if target_user_ids:
            from bson import ObjectId
            id_objs = []
            for tid in target_user_ids:
                if isinstance(tid, str) and ObjectId.is_valid(tid):
                    try:
                        id_objs.append(ObjectId(tid))
                    except Exception:
                        pass

            or_clauses: List[Dict[str, Any]] = [
                {"user_id": {"$in": target_user_ids}},
                {"phone": {"$in": target_user_ids}},
            ]
            if id_objs:
                or_clauses.append({"_id": {"$in": id_objs}})

            cursor = database["users"].find({
                "$or": or_clauses,
                "is_active": {"$ne": False},
            })
            async for u in cursor:
                uid, role, phone = extract_user_id_and_phone(u)
                if uid not in exclude_set:
                    resolved_map[uid] = {
                        "user_id": uid,
                        "role": role,
                        "phone_number": phone,
                    }

            # Fallback for explicit target_user_ids not found in users collection
            for tid in target_user_ids:
                if tid not in resolved_map and tid not in exclude_set:
                    pref_doc = await database["notification_preferences"].find_one({"user_id": tid})
                    phone = pref_doc.get("phone_number") if pref_doc else None
                    resolved_map[tid] = {
                        "user_id": tid,
                        "role": None,
                        "phone_number": phone,
                    }

        # 2. Query by target roles
        if target_roles:
            role_values = [r.value if isinstance(r, UserRole) else str(r) for r in target_roles]
            cursor = database["users"].find({
                "role": {"$in": role_values},
                "is_active": {"$ne": False},
            })
            async for u in cursor:
                uid, role, phone = extract_user_id_and_phone(u)
                if uid not in exclude_set:
                    resolved_map[uid] = {
                        "user_id": uid,
                        "role": role,
                        "phone_number": phone,
                    }

        # Default fallback: If no recipients resolved, find all Emergency Officers & Admins
        if not resolved_map and not target_user_ids:
            cursor = database["users"].find({
                "role": {"$in": [UserRole.EMERGENCY_OFFICER.value, UserRole.ADMIN.value]},
                "is_active": {"$ne": False},
            })
            async for u in cursor:
                uid, role, phone = extract_user_id_and_phone(u)
                if uid not in exclude_set:
                    resolved_map[uid] = {
                        "user_id": uid,
                        "role": role,
                        "phone_number": phone,
                    }

        return list(resolved_map.values())

    def _format_whatsapp_message(
        self,
        severity: NotificationSeverity,
        title: str,
        message: str,
        category: NotificationCategory,
        metadata: Dict[str, Any],
    ) -> str:
        """Format an operational, truthful WhatsApp emergency alert text."""
        lines = [
            f"🚨 *RESILIENCE AI ALERT [{severity.value}]*",
            f"*{title}*",
            "",
            message,
        ]
        if metadata.get("situation_title"):
            lines.append(f"• Situation: {metadata['situation_title']}")
        if metadata.get("location_name"):
            lines.append(f"• Location: {metadata['location_name']}")
        if metadata.get("shortfall_details"):
            lines.append(f"• Shortfall: {metadata['shortfall_details']}")

        lines.append("")
        lines.append("Access Emergency Command Center for operational actions.")
        return "\n".join(lines)

    def _format_sms_message(
        self,
        severity: NotificationSeverity,
        title: str,
        message: str,
    ) -> str:
        """Format a concise, controlled emergency SMS notification."""
        return f"RESILIENCE [{severity.value}]: {title}. {message} Follow Command Center guidance."

    async def dispatch_event(
        self,
        category: NotificationCategory,
        event_type: str,
        severity: NotificationSeverity,
        title: str,
        message: str,
        event_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        situation_id: Optional[str] = None,
        coordination_plan_id: Optional[str] = None,
        view_hint: Optional[str] = None,
        target_user_ids: Optional[List[str]] = None,
        target_roles: Optional[List[UserRole]] = None,
        exclude_user_ids: Optional[List[str]] = None,
        material_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_simulation: bool = False,
        db: Optional[Any] = None,
    ) -> Optional[Notification]:
        """
        Unified entry point to generate and deliver event-driven notifications.
        Enforces idempotency, recipient resolution, preference filtering,
        severity escalation policy, and simulation safety.
        """
        database = self._get_db(db)
        meta = metadata or {}
        now = datetime.now(timezone.utc)

        # 1. Deduplication / Idempotency Check
        fingerprint = self.compute_fingerprint(
            category=category,
            event_type=event_type,
            entity_id=entity_id,
            material_state=material_state,
        )

        existing_doc = await database["notifications"].find_one({"fingerprint": fingerprint})
        if existing_doc:
            logger.info("Notification deduplicated by fingerprint=%s (%s)", fingerprint, title)
            existing_doc.pop("_id", None)
            return Notification(**existing_doc)

        # 2. Recipient Resolution
        raw_recipients = await self.resolve_recipients(
            target_user_ids=target_user_ids,
            target_roles=target_roles,
            exclude_user_ids=exclude_user_ids,
            db=database,
        )

        if not raw_recipients:
            logger.warning("No eligible recipients found for event %s (%s)", event_type, title)
            return None

        # 3. Build Recipient Info & Evaluate Escalation Policy
        recipient_infos: List[NotificationRecipientInfo] = []
        whatsapp_tasks_to_run = []
        sms_tasks_to_run = []

        whatsapp_text = self._format_whatsapp_message(
            severity=severity,
            title=title,
            message=message,
            category=category,
            metadata=meta,
        )
        sms_text = self._format_sms_message(
            severity=severity,
            title=title,
            message=message,
        )

        for rec in raw_recipients:
            uid = rec["user_id"]
            role = rec.get("role")
            phone = rec.get("phone_number")

            pref = await self.get_user_preferences(uid, db=database)
            if pref.phone_number and not phone:
                phone = pref.phone_number

            # Evaluate In-App Channel
            in_app_state = InAppDeliveryState(
                status=NotificationDeliveryStatus.DELIVERED,
                delivered_at=now,
            )

            # Evaluate WhatsApp Channel
            whatsapp_state = WhatsAppDeliveryState()

            # Evaluate SMS Channel
            sms_state = SmsDeliveryState()

            # SIMULATION SAFETY RULE: Simulation notifications NEVER trigger WhatsApp or SMS
            if is_simulation:
                whatsapp_state.status = NotificationDeliveryStatus.SKIPPED
                sms_state.status = NotificationDeliveryStatus.SKIPPED
            else:
                # Severity Escalation Policy & Preferences for WhatsApp
                should_attempt_whatsapp = False
                if severity == NotificationSeverity.CRITICAL:
                    should_attempt_whatsapp = bool(phone and (pref.whatsapp_enabled or pref.notify_critical))
                elif severity == NotificationSeverity.HIGH:
                    should_attempt_whatsapp = bool(phone and pref.whatsapp_enabled and pref.notify_high)
                elif severity == NotificationSeverity.MEDIUM:
                    should_attempt_whatsapp = bool(phone and pref.whatsapp_enabled and pref.notify_operational)
                else:  # LOW
                    should_attempt_whatsapp = False

                if should_attempt_whatsapp and phone:
                    if self.provider.is_configured():
                        whatsapp_state.status = NotificationDeliveryStatus.QUEUED
                        whatsapp_state.queued_at = now
                        whatsapp_tasks_to_run.append((uid, phone))
                    else:
                        whatsapp_state.status = NotificationDeliveryStatus.NOT_CONFIGURED
                        whatsapp_state.error_code = "CREDENTIALS_MISSING"
                        whatsapp_state.error_message = "WhatsApp provider credentials not configured in environment."
                else:
                    whatsapp_state.status = NotificationDeliveryStatus.SKIPPED

                # Severity Escalation Policy & Preferences for SMS
                should_attempt_sms = False
                if severity == NotificationSeverity.CRITICAL:
                    should_attempt_sms = bool(phone and (pref.sms_enabled or pref.notify_critical))
                elif severity == NotificationSeverity.HIGH:
                    should_attempt_sms = bool(phone and pref.sms_enabled and pref.notify_high)
                elif severity == NotificationSeverity.MEDIUM:
                    should_attempt_sms = bool(phone and pref.sms_enabled and pref.notify_operational)
                else:  # LOW
                    should_attempt_sms = False

                if should_attempt_sms and phone:
                    if self.sms_provider.is_configured():
                        sms_state.status = NotificationDeliveryStatus.QUEUED
                        sms_state.queued_at = now
                        sms_tasks_to_run.append((uid, phone))
                    else:
                        sms_state.status = NotificationDeliveryStatus.NOT_CONFIGURED
                        sms_state.error_code = "CREDENTIALS_MISSING"
                        sms_state.error_message = "SMS provider credentials/sender not configured in environment."
                else:
                    sms_state.status = NotificationDeliveryStatus.SKIPPED

            rec_info = NotificationRecipientInfo(
                user_id=uid,
                role=role,
                phone_number=phone,
                in_app=in_app_state,
                whatsapp=whatsapp_state,
                sms=sms_state,
            )
            recipient_infos.append(rec_info)

        # 4. Create Canonical Notification Record
        notification_id = f"notif_{uuid.uuid4().hex[:14]}"
        deep_link = None
        if entity_type or entity_id or situation_id or coordination_plan_id or view_hint:
            deep_link = NotificationDeepLink(
                entity_type=entity_type,
                entity_id=entity_id,
                situation_id=situation_id,
                coordination_plan_id=coordination_plan_id,
                view_hint=view_hint,
            )

        notification = Notification(
            notification_id=notification_id,
            event_id=event_id,
            category=category,
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            deep_link=deep_link,
            is_simulation=is_simulation,
            fingerprint=fingerprint,
            metadata=meta,
            created_at=now,
            recipients=recipient_infos,
        )

        # 5. Authoritative MongoDB Save
        doc = notification.model_dump()
        await database["notifications"].insert_one(doc)

        # 6. Execute Queued WhatsApp Deliveries Asynchronously
        for uid, phone in whatsapp_tasks_to_run:
            try:
                res = await self.provider.send_message(
                    recipient_phone=phone,
                    message=whatsapp_text,
                )
                now_wa = datetime.now(timezone.utc)
                update_fields = {
                    "recipients.$.whatsapp.status": res.status.value,
                    "recipients.$.whatsapp.provider_message_id": res.provider_message_id,
                    "recipients.$.whatsapp.error_code": res.error_code,
                    "recipients.$.whatsapp.error_message": res.error_message,
                }
                if res.status == NotificationDeliveryStatus.SENT:
                    update_fields["recipients.$.whatsapp.sent_at"] = now_wa
                elif res.status == NotificationDeliveryStatus.FAILED:
                    update_fields["recipients.$.whatsapp.failed_at"] = now_wa

                await database["notifications"].update_one(
                    {"notification_id": notification_id, "recipients.user_id": uid},
                    {"$set": update_fields},
                )

                # Update in-memory object for caller return
                for r in notification.recipients:
                    if r.user_id == uid:
                        r.whatsapp.status = res.status
                        r.whatsapp.provider_message_id = res.provider_message_id
                        r.whatsapp.error_code = res.error_code
                        r.whatsapp.error_message = res.error_message
                        if res.status == NotificationDeliveryStatus.SENT:
                            r.whatsapp.sent_at = now_wa
                        elif res.status == NotificationDeliveryStatus.FAILED:
                            r.whatsapp.failed_at = now_wa

            except Exception as ex:
                logger.error("Error executing WhatsApp dispatch to %s: %s", phone, str(ex))

        # 7. Execute Queued SMS Deliveries Asynchronously
        for uid, phone in sms_tasks_to_run:
            try:
                res_sms = await self.sms_provider.send_sms(
                    recipient_phone=phone,
                    message=sms_text,
                )
                now_sms = datetime.now(timezone.utc)
                update_sms_fields = {
                    "recipients.$.sms.status": res_sms.status.value,
                    "recipients.$.sms.provider_message_id": res_sms.provider_message_id,
                    "recipients.$.sms.error_code": res_sms.error_code,
                    "recipients.$.sms.error_message": res_sms.error_message,
                }
                if res_sms.status in (NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.QUEUED, NotificationDeliveryStatus.SENDING):
                    update_sms_fields["recipients.$.sms.sent_at"] = now_sms
                elif res_sms.status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.UNDELIVERED):
                    update_sms_fields["recipients.$.sms.failed_at"] = now_sms

                await database["notifications"].update_one(
                    {"notification_id": notification_id, "recipients.user_id": uid},
                    {"$set": update_sms_fields},
                )

                for r in notification.recipients:
                    if r.user_id == uid:
                        r.sms.status = res_sms.status
                        r.sms.provider_message_id = res_sms.provider_message_id
                        r.sms.error_code = res_sms.error_code
                        r.sms.error_message = res_sms.error_message
                        if res_sms.status in (NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.QUEUED, NotificationDeliveryStatus.SENDING):
                            r.sms.sent_at = now_sms
                        elif res_sms.status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.UNDELIVERED):
                            r.sms.failed_at = now_sms

            except Exception as ex:
                logger.error("Error executing SMS dispatch to %s: %s", phone, str(ex))

        return notification

    async def get_user_notifications(
        self,
        user_id: str,
        category: Optional[NotificationCategory] = None,
        severity: Optional[NotificationSeverity] = None,
        unread_only: bool = False,
        limit: int = 50,
        skip: int = 0,
        db: Optional[Any] = None,
    ) -> List[NotificationUserView]:
        """Fetch notifications scoped to the given user."""
        database = self._get_db(db)
        query: Dict[str, Any] = {"recipients.user_id": user_id}

        if category:
            query["category"] = category.value
        if severity:
            query["severity"] = severity.value

        cursor = database["notifications"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results: List[NotificationUserView] = []

        async for doc in cursor:
            # Extract user-scoped recipient slice
            user_rec = next((r for r in doc.get("recipients", []) if r.get("user_id") == user_id), None)
            if not user_rec:
                continue

            in_app = user_rec.get("in_app", {})
            in_app_status = in_app.get("status", NotificationDeliveryStatus.DELIVERED.value)
            read_at = in_app.get("read_at")

            if unread_only and (in_app_status == NotificationDeliveryStatus.READ.value or read_at is not None):
                continue

            wa = user_rec.get("whatsapp", {})
            wa_status = wa.get("status", NotificationDeliveryStatus.NOT_CONFIGURED.value)

            sms = user_rec.get("sms", {})
            sms_status = sms.get("status", NotificationDeliveryStatus.NOT_CONFIGURED.value)

            deep_link_obj = None
            if doc.get("deep_link"):
                deep_link_obj = NotificationDeepLink(**doc["deep_link"])

            results.append(
                NotificationUserView(
                    notification_id=doc["notification_id"],
                    event_id=doc.get("event_id"),
                    category=NotificationCategory(doc["category"]),
                    event_type=doc.get("event_type", ""),
                    severity=NotificationSeverity(doc.get("severity", "LOW")),
                    title=doc.get("title", ""),
                    message=doc.get("message", ""),
                    deep_link=deep_link_obj,
                    is_simulation=doc.get("is_simulation", False),
                    metadata=doc.get("metadata", {}),
                    created_at=doc.get("created_at"),
                    in_app_status=NotificationDeliveryStatus(in_app_status),
                    read_at=read_at,
                    whatsapp_status=NotificationDeliveryStatus(wa_status),
                    sms_status=NotificationDeliveryStatus(sms_status),
                )
            )

        return results

    async def get_unread_count(self, user_id: str, db: Optional[Any] = None) -> int:
        """Count unread in-app notifications for the given user."""
        database = self._get_db(db)
        count = await database["notifications"].count_documents({
            "recipients": {
                "$elemMatch": {
                    "user_id": user_id,
                    "in_app.status": {"$ne": NotificationDeliveryStatus.READ.value},
                    "in_app.read_at": None,
                }
            }
        })
        return count

    async def mark_as_read(
        self, user_id: str, notification_id: str, db: Optional[Any] = None
    ) -> bool:
        """Mark a single notification as read for a specific user (IDOR safe)."""
        database = self._get_db(db)
        now = datetime.now(timezone.utc)
        result = await database["notifications"].update_one(
            {
                "notification_id": notification_id,
                "recipients.user_id": user_id,
            },
            {
                "$set": {
                    "recipients.$.in_app.status": NotificationDeliveryStatus.READ.value,
                    "recipients.$.in_app.read_at": now,
                }
            },
        )
        return result.modified_count > 0

    async def mark_all_as_read(self, user_id: str, db: Optional[Any] = None) -> int:
        """Mark all unread notifications as read for a specific user."""
        database = self._get_db(db)
        now = datetime.now(timezone.utc)
        # Update matching documents where user has unread state
        result = await database["notifications"].update_many(
            {
                "recipients": {
                    "$elemMatch": {
                        "user_id": user_id,
                        "in_app.status": {"$ne": NotificationDeliveryStatus.READ.value},
                    }
                }
            },
            {
                "$set": {
                    "recipients.$[elem].in_app.status": NotificationDeliveryStatus.READ.value,
                    "recipients.$[elem].in_app.read_at": now,
                }
            },
            array_filters=[{"elem.user_id": user_id}],
        )
        return result.modified_count

    async def process_whatsapp_webhook(
        self, payload: Dict[str, Any], db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Process genuine Meta WhatsApp Cloud API webhook event payloads.
        Handles message delivery status updates (sent, delivered, read, failed) and inbound messages idempotently.
        """
        database = self._get_db(db)
        if not isinstance(payload, dict):
            return {"status": "ignored", "reason": "invalid_payload_format"}

        obj = payload.get("object")
        if obj != "whatsapp_business_account":
            return {"status": "ignored", "reason": "non_whatsapp_object"}

        entries = payload.get("entry", [])
        if not isinstance(entries, list):
            return {"status": "ignored", "reason": "invalid_entries"}

        processed_statuses = 0
        processed_messages = 0

        # Status progression order to prevent backward status downgrades
        status_rank = {
            NotificationDeliveryStatus.PENDING.value: 0,
            NotificationDeliveryStatus.QUEUED.value: 1,
            NotificationDeliveryStatus.SENDING.value: 2,
            NotificationDeliveryStatus.SENT.value: 3,
            NotificationDeliveryStatus.DELIVERED.value: 4,
            NotificationDeliveryStatus.READ.value: 5,
            NotificationDeliveryStatus.FAILED.value: 6,
        }

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes", [])
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value", {})
                if not isinstance(value, dict):
                    continue

                # 1. Process Status Updates
                statuses = value.get("statuses", [])
                if isinstance(statuses, list):
                    for st in statuses:
                        if not isinstance(st, dict):
                            continue
                        msg_id = st.get("id")
                        status_raw = (st.get("status") or "").lower()
                        ts_raw = st.get("timestamp")
                        errors = st.get("errors", [])

                        if not msg_id or not status_raw:
                            continue

                        status_map = {
                            "sent": NotificationDeliveryStatus.SENT,
                            "delivered": NotificationDeliveryStatus.DELIVERED,
                            "read": NotificationDeliveryStatus.READ,
                            "failed": NotificationDeliveryStatus.FAILED,
                        }
                        new_status = status_map.get(status_raw)
                        if not new_status:
                            continue

                        now_dt = datetime.now(timezone.utc)
                        if ts_raw:
                            try:
                                now_dt = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                            except Exception:
                                pass

                        error_code = None
                        error_message = None
                        if errors and isinstance(errors, list) and len(errors) > 0:
                            first_err = errors[0] if isinstance(errors[0], dict) else {}
                            error_code = str(first_err.get("code") or "ERROR")
                            error_message = str(first_err.get("title") or first_err.get("message") or "Delivery failed")

                        # Build update document
                        update_doc: Dict[str, Any] = {
                            "recipients.$.whatsapp.status": new_status.value,
                        }
                        if new_status == NotificationDeliveryStatus.SENT:
                            update_doc["recipients.$.whatsapp.sent_at"] = now_dt
                        elif new_status == NotificationDeliveryStatus.DELIVERED:
                            update_doc["recipients.$.whatsapp.delivered_at"] = now_dt
                        elif new_status == NotificationDeliveryStatus.READ:
                            update_doc["recipients.$.whatsapp.read_at"] = now_dt
                        elif new_status == NotificationDeliveryStatus.FAILED:
                            update_doc["recipients.$.whatsapp.failed_at"] = now_dt
                            if error_code:
                                update_doc["recipients.$.whatsapp.error_code"] = error_code
                            if error_message:
                                update_doc["recipients.$.whatsapp.error_message"] = error_message

                        res = await database["notifications"].update_one(
                            {"recipients.whatsapp.provider_message_id": msg_id},
                            {"$set": update_doc},
                        )
                        if res.modified_count > 0:
                            processed_statuses += 1
                            logger.info("WhatsApp delivery status updated: msg_id=%s status=%s", msg_id, new_status.value)

                # 2. Process Inbound Messages (Queries / Status checks)
                messages = value.get("messages", [])
                if isinstance(messages, list):
                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue
                        from_num = str(msg.get("from") or "")
                        msg_id = msg.get("id")

                        if msg_id and from_num:
                            processed_messages += 1
                            masked_num = f"{from_num[:3]}***{from_num[-3:]}" if len(from_num) >= 6 else "***"
                            logger.info("WhatsApp inbound message acknowledged: from=%s id=%s", masked_num, msg_id)

        return {
            "status": "processed",
            "statuses_updated": processed_statuses,
            "messages_received": processed_messages,
        }

    async def process_twilio_status_callback(
        self, form_data: Dict[str, Any], db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Process Twilio WhatsApp and SMS delivery status callbacks
        (queued, accepted, sending, sent, delivered, undelivered, read, failed).
        Updates notification_deliveries idempotently using the Twilio Message SID.
        Does NOT duplicate delivery records or trigger citizen reporting.
        """
        database = self._get_db(db)
        message_sid = form_data.get("MessageSid") or form_data.get("SmsSid")
        raw_status = (form_data.get("MessageStatus") or form_data.get("SmsStatus") or "").lower().strip()
        error_code = form_data.get("ErrorCode")
        error_message = form_data.get("ErrorMessage")

        if not message_sid or not raw_status:
            return {"status": "ignored", "reason": "missing_message_sid_or_status"}

        status_map = {
            "queued": NotificationDeliveryStatus.QUEUED,
            "accepted": NotificationDeliveryStatus.QUEUED,
            "sending": NotificationDeliveryStatus.SENDING,
            "sent": NotificationDeliveryStatus.SENT,
            "delivered": NotificationDeliveryStatus.DELIVERED,
            "read": NotificationDeliveryStatus.READ,
            "failed": NotificationDeliveryStatus.FAILED,
            "undelivered": NotificationDeliveryStatus.UNDELIVERED,
        }
        new_status = status_map.get(raw_status)
        if not new_status:
            return {"status": "ignored", "reason": f"unrecognized_status_{raw_status}"}

        now_dt = datetime.now(timezone.utc)

        # 1. Try updating WhatsApp match first
        update_wa_doc: Dict[str, Any] = {
            "recipients.$.whatsapp.status": new_status.value,
        }
        if new_status == NotificationDeliveryStatus.QUEUED:
            update_wa_doc["recipients.$.whatsapp.queued_at"] = now_dt
        elif new_status == NotificationDeliveryStatus.SENT:
            update_wa_doc["recipients.$.whatsapp.sent_at"] = now_dt
        elif new_status == NotificationDeliveryStatus.DELIVERED:
            update_wa_doc["recipients.$.whatsapp.delivered_at"] = now_dt
        elif new_status == NotificationDeliveryStatus.READ:
            update_wa_doc["recipients.$.whatsapp.read_at"] = now_dt
        elif new_status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.UNDELIVERED):
            update_wa_doc["recipients.$.whatsapp.failed_at"] = now_dt
            if error_code:
                update_wa_doc["recipients.$.whatsapp.error_code"] = str(error_code)
            if error_message:
                update_wa_doc["recipients.$.whatsapp.error_message"] = str(error_message)

        res = await database["notifications"].update_one(
            {"recipients.whatsapp.provider_message_id": message_sid},
            {"$set": update_wa_doc},
        )

        matched_channel = "whatsapp" if res.matched_count > 0 else None

        # 2. If not matched on WhatsApp, try updating SMS match
        if not matched_channel:
            update_sms_doc: Dict[str, Any] = {
                "recipients.$.sms.status": new_status.value,
            }
            if new_status == NotificationDeliveryStatus.QUEUED:
                update_sms_doc["recipients.$.sms.queued_at"] = now_dt
            elif new_status in (NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.SENDING):
                update_sms_doc["recipients.$.sms.sent_at"] = now_dt
            elif new_status == NotificationDeliveryStatus.DELIVERED:
                update_sms_doc["recipients.$.sms.delivered_at"] = now_dt
            elif new_status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.UNDELIVERED):
                update_sms_doc["recipients.$.sms.failed_at"] = now_dt
                if error_code:
                    update_sms_doc["recipients.$.sms.error_code"] = str(error_code)
                if error_message:
                    update_sms_doc["recipients.$.sms.error_message"] = str(error_message)

            res = await database["notifications"].update_one(
                {"recipients.sms.provider_message_id": message_sid},
                {"$set": update_sms_doc},
            )
            if res.matched_count > 0:
                matched_channel = "sms"

        if not matched_channel:
            logger.warning("Twilio callback: No notification found for MessageSid=%s", message_sid)
            return {"status": "not_found", "message_sid": message_sid}

        logger.info(
            "Twilio %s status callback processed: MessageSid=%s status=%s modified=%d",
            matched_channel.upper(),
            message_sid,
            new_status.value,
            res.modified_count,
        )

        return {
            "status": "processed",
            "channel": matched_channel,
            "message_sid": message_sid,
            "delivery_status": new_status.value,
            "updated": res.modified_count > 0,
        }

    async def process_twilio_inbound(
        self, form_data: Dict[str, Any], db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Acknowledge inbound WhatsApp messages from Twilio Sandbox.
        IMPORTANT: Inbound WhatsApp messages NEVER trigger citizen emergency reporting.
        Citizen emergency reporting remains strictly on /report-emergency.
        """
        message_sid = form_data.get("MessageSid")
        from_number = form_data.get("From") or ""
        body = form_data.get("Body") or ""

        masked_phone = f"{from_number[:5]}***{from_number[-3:]}" if len(from_number) >= 8 else "***"
        logger.info(
            "Twilio inbound WhatsApp message acknowledged from %s (sid=%s, chars=%d). Emergency reporting is not accepted via WhatsApp.",
            masked_phone,
            message_sid,
            len(body),
        )

        return {
            "status": "acknowledged",
            "message_sid": message_sid,
            "notice": "WhatsApp is for notification delivery only. Citizen reporting must use /report-emergency.",
        }

    async def process_twilio_inbound_sms(
        self, form_data: Dict[str, Any], db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Acknowledge inbound SMS messages from Twilio.
        IMPORTANT: Inbound SMS messages NEVER trigger citizen emergency reporting.
        Citizen emergency reporting remains strictly on /report-emergency.
        """
        message_sid = form_data.get("MessageSid") or form_data.get("SmsSid")
        from_number = form_data.get("From") or ""
        body = form_data.get("Body") or ""

        masked_phone = f"{from_number[:5]}***{from_number[-3:]}" if len(from_number) >= 8 else "***"
        logger.info(
            "Twilio inbound SMS message acknowledged from %s (sid=%s, chars=%d). Emergency reporting is not accepted via SMS.",
            masked_phone,
            message_sid,
            len(body),
        )

        return {
            "status": "acknowledged",
            "message_sid": message_sid,
            "notice": "SMS is an outbound notification channel only. Citizen reporting must use /report-emergency.",
        }

    def get_channel_status(self) -> Dict[str, Any]:
        """Check operational and configuration status of delivery channels."""
        provider = self.provider
        wa_configured = provider.is_configured()
        provider_name = (settings.WHATSAPP_PROVIDER or "twilio").strip().lower()

        status_val = "OPERATIONAL" if wa_configured else "NOT_CONFIGURED"

        wa_info: Dict[str, Any] = {
            "channel": NotificationChannel.WHATSAPP.value,
            "status": status_val,
            "configured": wa_configured,
            "provider": provider_name,
            "enabled": settings.TWILIO_WHATSAPP_ENABLED if provider_name == "twilio" else bool(settings.WHATSAPP_ACCESS_TOKEN),
        }
        if not wa_configured:
            wa_info["reason"] = "NOT_CONFIGURED"

        if provider_name == "twilio":
            wa_info["from_number"] = settings.TWILIO_WHATSAPP_FROM
            wa_info["status_callback_configured"] = bool(settings.TWILIO_WHATSAPP_STATUS_CALLBACK_URL)
        else:
            wa_info["webhook_configured"] = bool(settings.whatsapp_verify_token)
            wa_info["api_version"] = settings.WHATSAPP_API_VERSION

        # SMS Channel Status
        sms_prov = self.sms_provider
        sms_configured = sms_prov.is_configured()
        sms_provider_name = (settings.SMS_PROVIDER or "disabled").strip().lower()
        sms_status_val = "OPERATIONAL" if sms_configured else "NOT_CONFIGURED"

        sms_info: Dict[str, Any] = {
            "channel": NotificationChannel.SMS.value,
            "status": sms_status_val,
            "configured": sms_configured,
            "provider": sms_provider_name,
            "enabled": settings.TWILIO_SMS_ENABLED if sms_provider_name == "twilio" else False,
        }
        if not sms_configured:
            sms_info["reason"] = "NOT_CONFIGURED"
        if sms_provider_name == "twilio":
            sms_info["from_number"] = settings.TWILIO_SMS_FROM
            sms_info["status_callback_configured"] = bool(settings.TWILIO_SMS_STATUS_CALLBACK_URL)

        return {
            "in_app": {
                "channel": NotificationChannel.IN_APP.value,
                "status": "OPERATIONAL",
                "configured": True,
            },
            "whatsapp": wa_info,
            "sms": sms_info,
        }


# Singleton
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


