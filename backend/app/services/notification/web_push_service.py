import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from motor.motor_asyncio import AsyncIOMotorDatabase
import pywebpush

import hashlib
import uuid
from app.core.config import settings
from app.db.mongodb import db_manager
from app.models.enums import PushSubscriptionStatus, SafetyNotificationType
from app.models.safety_guidance import (
    PushSubscriptionCreate,
    PushSubscriptionRecord,
    PushNotificationPayload,
    PushDeliveryRecord,
    CitizenSafetyGuidance,
)

logger = logging.getLogger("resilience.web_push")


class WebPushService:
    _generated_vapid_private_pem: Optional[str] = None
    _generated_vapid_public_b64: Optional[str] = None
    _vapid_instance: Optional[Any] = None

    @classmethod
    def _init_vapid_keys(cls) -> None:
        """
        Initializes or loads persistent NIST P-256 VAPID cryptographic keys.
        """
        from py_vapid import Vapid

        if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY:
            try:
                cls._vapid_instance = Vapid.from_pem(settings.VAPID_PRIVATE_KEY.encode("utf-8"))
                cls._generated_vapid_public_b64 = settings.VAPID_PUBLIC_KEY
                cls._generated_vapid_private_pem = settings.VAPID_PRIVATE_KEY
                return
            except Exception as pem_err:
                logger.warning(f"Could not initialize VAPID instance from settings PEM: {pem_err}")

        if cls._vapid_instance and cls._generated_vapid_private_pem and cls._generated_vapid_public_b64:
            return

        import os
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        candidate_paths = [
            os.path.join(backend_dir, "vapid_keys.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "vapid_keys.json"),
        ]
        for key_file_path in candidate_paths:
            if os.path.exists(key_file_path):
                try:
                    with open(key_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("public_key") and data.get("private_key"):
                            cls._vapid_instance = Vapid.from_pem(data["private_key"].encode("utf-8"))
                            cls._generated_vapid_public_b64 = data["public_key"]
                            cls._generated_vapid_private_pem = data["private_key"]
                            logger.info(f"Loaded persistent VAPID EC keypair from {key_file_path}.")
                            return
                except Exception as read_err:
                    logger.warning(f"Could not read persistent VAPID keyfile {key_file_path}: {read_err}")

        try:
            v = Vapid()
            v.generate_keys()
            cls._vapid_instance = v
            private_pem = v.private_pem().decode("utf-8")
            raw_pub_bytes = v.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
            import base64
            public_b64 = base64.urlsafe_b64encode(raw_pub_bytes).decode("utf-8").rstrip("=")

            cls._generated_vapid_private_pem = private_pem
            cls._generated_vapid_public_b64 = public_b64
            try:
                with open(key_file_path, "w", encoding="utf-8") as f:
                    json.dump({"public_key": public_b64, "private_key": private_pem}, f)
            except Exception:
                pass
            logger.info("Initialized and persisted secure VAPID EC keypair for Web Push.")
        except Exception as e:
            logger.error(f"Failed to generate VAPID keys: {e}")

    @classmethod
    def get_public_vapid_key(cls) -> str:
        """Returns the URL-safe base64 uncompressed public VAPID key for browser subscription."""
        cls._init_vapid_keys()
        return cls._generated_vapid_public_b64 or ""

    @classmethod
    def get_private_vapid_key(cls) -> str:
        cls._init_vapid_keys()
        return cls._generated_vapid_private_pem or ""

    @classmethod
    def get_vapid_instance(cls) -> Optional[Any]:
        cls._init_vapid_keys()
        return cls._vapid_instance

    @classmethod
    async def save_subscription(
        cls,
        sub_in: PushSubscriptionCreate,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> PushSubscriptionRecord:
        """
        Idempotently persists or updates a browser Web Push subscription.
        Links anonymous sessions and report IDs without creating duplicate records.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("MongoDB database connection is not initialized.")

        fingerprint = PushSubscriptionRecord.compute_fingerprint(sub_in.endpoint, sub_in.keys.p256dh)
        now_utc = datetime.now(timezone.utc)

        existing = await db["push_subscriptions"].find_one({
            "$or": [
                {"subscription_fingerprint": fingerprint},
                {"endpoint": sub_in.endpoint},
            ]
        })

        if existing:
            update_fields: Dict[str, Any] = {
                "status": PushSubscriptionStatus.ACTIVE.value,
                "updated_at": now_utc,
                "last_seen_at": now_utc,
                "p256dh": sub_in.keys.p256dh,
                "auth": sub_in.keys.auth,
                "subscription_fingerprint": fingerprint,
            }
            if sub_in.user_agent:
                update_fields["user_agent"] = sub_in.user_agent

            push_ops: Dict[str, Any] = {}
            if sub_in.report_id:
                push_ops["report_ids"] = sub_in.report_id
            if sub_in.session_id:
                push_ops["session_ids"] = sub_in.session_id

            update_doc: Dict[str, Any] = {"$set": update_fields}
            if push_ops:
                update_doc["$addToSet"] = push_ops

            await db["push_subscriptions"].update_one(
                {"_id": existing["_id"]},
                update_doc,
            )

            updated = await db["push_subscriptions"].find_one({"_id": existing["_id"]})
            return cls._doc_to_record(updated)

        import secrets
        sub_id = f"SUB-{secrets.token_hex(6).upper()}"
        record = PushSubscriptionRecord(
            subscription_id=sub_id,
            endpoint=sub_in.endpoint,
            p256dh=sub_in.keys.p256dh,
            auth=sub_in.keys.auth,
            user_agent=sub_in.user_agent,
            status=PushSubscriptionStatus.ACTIVE,
            created_at=now_utc,
            updated_at=now_utc,
            last_seen_at=now_utc,
            report_ids=[sub_in.report_id] if sub_in.report_id else [],
            session_ids=[sub_in.session_id] if sub_in.session_id else [],
            subscription_fingerprint=fingerprint,
        )

        doc = record.model_dump()
        await db["push_subscriptions"].insert_one(doc)
        logger.info(f"Registered new Web Push subscription: {sub_id} (Fingerprint: {fingerprint[:12]}...)")
        return record

    @classmethod
    async def remove_subscription(
        cls,
        endpoint: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> bool:
        """Marks a Web Push subscription as unsubscribed."""
        if db is None:
            db = db_manager.db
        if db is None:
            return False

        res = await db["push_subscriptions"].update_many(
            {"endpoint": endpoint},
            {"$set": {"status": PushSubscriptionStatus.UNSUBSCRIBED.value, "updated_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count > 0

    @classmethod
    async def send_web_push(
        cls,
        subscription: PushSubscriptionRecord,
        payload: PushNotificationPayload,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> bool:
        """
        Sends an RFC 8291 encrypted Web Push notification to a subscribed client browser.
        Accurately differentiates 201 Created, 401 VAPID Auth, 404/410 Expired, 400 Bad Request,
        429 Rate Limited, 5xx Provider Error, and Network/Timeout.
        """
        cls._init_vapid_keys()
        private_key = cls.get_private_vapid_key()
        if not private_key:
            logger.error("Cannot send web push: VAPID private key is unavailable.")
            return False

        sub_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        now_utc = datetime.now(timezone.utc)
        sub_claim = (settings.VAPID_CLAIMS_EMAIL or "mailto:emergency-alerts@resilience-civildefense.org").strip()
        if "@" in sub_claim and not sub_claim.startswith("mailto:") and not sub_claim.startswith("http"):
            sub_claim = f"mailto:{sub_claim}"

        claims = {
            "sub": sub_claim,
        }

        vapid_target = cls.get_vapid_instance() or private_key
        try:
            pywebpush.webpush(
                subscription_info=sub_info,
                data=payload.model_dump_json(),
                vapid_private_key=vapid_target,
                vapid_claims=claims,
                ttl=3600,
            )
            logger.info(f"Web push dispatched successfully to {subscription.subscription_id}.")
            if db is not None:
                await db["push_subscriptions"].update_one(
                    {"subscription_id": subscription.subscription_id},
                    {
                        "$set": {
                            "last_success_at": now_utc,
                            "last_seen_at": now_utc,
                            "last_provider_status": "ACCEPTED_201",
                            "last_delivery_status": "DELIVERED",
                            "failure_reason": None,
                        }
                    },
                )
            return True

        except pywebpush.WebPushException as ex:
            logger.warning(f"Web push delivery failed for {subscription.subscription_id}: {ex}")
            status_code = getattr(getattr(ex, "response", None), "status_code", None)
            new_status = subscription.status

            if status_code in [404, 410]:
                # 404 / 410 Subscription Expired or Gone
                new_status = PushSubscriptionStatus.EXPIRED
                provider_status = f"{status_code}_SUBSCRIPTION_EXPIRED"
            elif status_code == 403:
                # 403 VAPID Key Mismatch / Forbidden - Mark expired so client resubscribes with current VAPID key
                new_status = PushSubscriptionStatus.EXPIRED
                provider_status = "403_VAPID_KEY_MISMATCH"
            elif status_code == 401:
                # 401 VAPID Authentication Error
                provider_status = "401_VAPID_AUTH_ERROR"
            elif status_code == 400:
                # 400 Invalid Subscription / Bad Request
                provider_status = "400_INVALID_SUBSCRIPTION"
            elif status_code == 429:
                # 429 Rate Limited (Transient)
                provider_status = "429_RATE_LIMITED"
            elif status_code and 500 <= status_code <= 599:
                # 5xx Provider Server Error (Transient)
                provider_status = f"{status_code}_PROVIDER_ERROR"
            else:
                provider_status = f"{status_code or 'UNKNOWN'}_PUSH_ERROR"

            if db is not None:
                await db["push_subscriptions"].update_one(
                    {"subscription_id": subscription.subscription_id},
                    {
                        "$set": {
                            "status": new_status.value,
                            "last_failure_at": now_utc,
                            "last_provider_status": provider_status,
                            "last_delivery_status": "FAILED",
                            "failure_reason": str(ex),
                        }
                    },
                )
            return False
        except Exception as e:
            logger.error(f"Unexpected error in web push delivery: {e}")
            if db is not None:
                await db["push_subscriptions"].update_one(
                    {"subscription_id": subscription.subscription_id},
                    {
                        "$set": {
                            "last_failure_at": now_utc,
                            "last_provider_status": "NETWORK_OR_INTERNAL_ERROR",
                            "last_delivery_status": "FAILED",
                            "failure_reason": str(e),
                        }
                    },
                )
            return False

    @classmethod
    def get_controlled_payload(
        cls,
        guidance: CitizenSafetyGuidance,
        notification_type: SafetyNotificationType = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED,
    ) -> PushNotificationPayload:
        """
        Generates controlled, non-hallucinated push notification content based on verified event type
        and the citizen's detected or preferred language.
        """
        lang_dict = getattr(guidance, "language", None) or {}
        lang_code = (lang_dict.get("code") if isinstance(lang_dict, dict) else "en") or "en"
        lang_code = lang_code.lower()

        templates = {
            "te": {
                "ready_title": "🚨 అత్యవసర భద్రతా మార్గదర్శకం ({emergency_type})",
                "ready_body": "ధృవీకరించబడిన సురక్షిత గమ్యస్థానం సిఫార్సు చేయబడింది.{dest_details} ప్రత్యక్ష మార్గాన్ని చూడటానికి నొక్కండి.",
                "route_updated_title": "⚠️ భద్రతా మార్గం నవీకరించబడింది",
                "route_updated_body": "ప్రస్తుత పరిస్థితుల దృష్ట్యా ప్రయాణ మార్గం నవీకరించబడింది.{dest_details} తాజా మార్గాన్ని చూడటానికి నొక్కండి.",
                "dest_updated_title": "📍 గమ్యస్థానం నవీకరించబడింది",
                "dest_updated_body": "సదుపాయాల లభ్యత ఆధారంగా పునరావాస కేంద్రం నవీకరించబడింది.{dest_details} వీక్షించడానికి నొక్కండి.",
                "route_unsafe_title": "⛔ మార్గం తాత్కాలికంగా సురక్షితం కాదు",
                "route_unsafe_body": "ప్రమాదకర పరిస్థితుల కారణంగా ప్రయాణ మార్గాలు మూసివేయబడ్డాయి. సురక్షిత ప్రదేశంలోనే ఆశ్రయం పొందండి.",
                "hazard_title": "⚠️ సమీప ప్రమాద హెచ్చరిక",
                "hazard_body": "మీ సమీపంలో ప్రమాదకర పరిస్థితి గుర్తించబడింది. జాగ్రత్తలను సమీక్షించండి.",
                "evac_approved_title": "🛡️ తరలింపు మార్గదర్శకం ఆమోదించబడింది",
                "evac_approved_body": "కమాండ్ సెంటర్ మీ తరలింపు మార్గాన్ని ఆమోదించింది.{dest_details} మార్గాన్ని చూడటానికి నొక్కండి.",
                "expired_title": "⏱️ భద్రతా మార్గదర్శకం గడువు ముగిసింది",
                "expired_body": "మునుపటి మార్గదర్శక గడువు ముగిసింది. తాజా సమాచారం కోసం నొక్కండి.",
                "default_title": "🚨 అత్యవసర సమాచార నవీకరణ ({emergency_type})",
                "default_body": "మీ నివేదికకు సంబంధించిన సమాచారం నవీకరించబడింది.{dest_details} వీక్షించడానికి నొక్కండి.",
                "rec_prefix": " సిఫార్సు: {name} ({dist} · {eta}).",
                "rec_prefix_simple": " సిఫార్సు: {name}.",
            },
            "hi": {
                "ready_title": "🚨 आपातकालीन सुरक्षा मार्गदर्शन ({emergency_type})",
                "ready_body": "एक सत्यापित सुरक्षा गंतव्य अनुशंसित किया गया है।{dest_details} लाइव मार्ग देखने के लिए टैप करें।",
                "route_updated_title": "⚠️ सुरक्षा मार्ग अपडेट किया गया",
                "route_updated_body": "सक्रिय परिस्थितियों के कारण पारगमन गलियारा अपडेट किया गया।{dest_details} नवीनतम मार्ग देखें।",
                "dest_updated_title": "📍 गंतव्य अपडेट किया गया",
                "dest_updated_body": "उपलब्धता के आधार पर आपातकालीन सुविधा अपडेट की गई।{dest_details} देखने के लिए टैप करें।",
                "route_unsafe_title": "⛔ मार्ग अस्थायी रूप से असुरक्षित",
                "route_unsafe_body": "सक्रिय खतरों के कारण मार्ग अवरुद्ध हैं। सुरक्षित स्थान पर आश्रय लें।",
                "hazard_title": "⚠️ निकटवर्ती खतरा चेतावनी",
                "hazard_body": "आपके निकट एक सक्रिय खतरा देखा गया है। सुरक्षा सावधानियों की समीक्षा करें।",
                "evac_approved_title": "🛡️ निकासी मार्गदर्शन स्वीकृत",
                "evac_approved_body": "कमांड ने आपके निकासी मार्ग को मंजूरी दे दी है।{dest_details} देखने के लिए टैप करें।",
                "expired_title": "⏱️ सुरक्षा मार्गदर्शन समाप्त",
                "expired_body": "पिछला मार्गदर्शन समाप्त हो गया है। वास्तविक समय की स्थिति के लिए टैप करें।",
                "default_title": "🚨 आपातकालीन सुरक्षा अपडेट ({emergency_type})",
                "default_body": "आपकी रिपोर्ट के लिए सुरक्षा जानकारी अपडेट की गई।{dest_details} देखने के लिए टैप करें।",
                "rec_prefix": " अनुशंसित: {name} ({dist} · {eta}).",
                "rec_prefix_simple": " अनुशंसित: {name}.",
            },
            "ta": {
                "ready_title": "🚨 அவசர பாதுகாப்பு வழிகாட்டுதல் ({emergency_type})",
                "ready_body": "சரிபார்க்கப்பட்ட பாதுகாப்பு மையம் பரிந்துரைக்கப்பட்டுள்ளது.{dest_details} வழியைக் காண தட்டவும்.",
                "route_updated_title": "⚠️ பாதுகாப்பு பாதை மாற்றப்பட்டது",
                "route_updated_body": "தற்போதைய நிலைமை காரணமாக பாதை புதுப்பிக்கப்பட்டுள்ளது.{dest_details} சமீபத்திய வழியைக் காணவும்.",
                "dest_updated_title": "📍 மையம் மாற்றப்பட்டது",
                "dest_updated_body": "கிடைக்கும் வசதிகளின் அடிப்படையில் மையம் மாற்றப்பட்டுள்ளது.{dest_details} பார்க்க தட்டவும்.",
                "route_unsafe_title": "⛔ பாதை தற்காலிகமாக பாதுகாப்பற்றது",
                "route_unsafe_body": "ஆபத்தான சூழலால் பாதை மூடப்பட்டுள்ளது. உள்ளேயே பாதுகாப்பாக இருங்கள்.",
                "hazard_title": "⚠️ அருகிலுள்ள ஆபத்து எச்சரிக்கை",
                "hazard_body": "உங்கள் பகுதியில் ஆபத்து கண்டறியப்பட்டுள்ளது. முன்னெச்சரிக்கைகளைப் பார்க்கவும்.",
                "evac_approved_title": "🛡️ வெளியேற்ற வழிகாட்டுதல் அங்கீகரிக்கப்பட்டது",
                "evac_approved_body": "அவசர கட்டுப்பாட்டு மையம் பாதையை அங்கீகரித்துள்ளது.{dest_details} பார்க்க தட்டவும்.",
                "expired_title": "⏱️ வழிகாட்டுதல் காலாவதியானது",
                "expired_body": "வழிகாட்டுதல் காலாவதியானது. நேரலை தகவலுக்கு தட்டவும்.",
                "default_title": "🚨 அவசர பாதுகாப்பு புதுப்பிப்பு ({emergency_type})",
                "default_body": "உங்கள் புகாருக்கான தகவல் புதுப்பிக்கப்பட்டுள்ளது.{dest_details} பார்க்க தட்டவும்.",
                "rec_prefix": " பரிந்துரை: {name} ({dist} · {eta}).",
                "rec_prefix_simple": " பரிந்துரை: {name}.",
            },
        }

        t_dict = templates.get(lang_code, {})

        dest_details = ""
        if guidance.recommended_destination:
            dest = guidance.recommended_destination
            dest_name = dest.destination_name
            dist_km = f"{dest.distance_km} km" if dest.distance_km is not None else ""
            eta = f"~{int(dest.estimated_drive_minutes)} min" if dest.estimated_drive_minutes else ""
            if dist_km and eta:
                rec_fmt = t_dict.get("rec_prefix", " Recommended: {name} ({dist} · {eta}).")
                dest_details = rec_fmt.format(name=dest_name, dist=dist_km, eta=eta)
            else:
                rec_fmt = t_dict.get("rec_prefix_simple", " Recommended: {name}.")
                dest_details = rec_fmt.format(name=dest_name)

        em_type = guidance.emergency_type or "General"

        if notification_type == SafetyNotificationType.SAFETY_GUIDANCE_READY:
            title = t_dict.get("ready_title", "🚨 Emergency Safety Guidance ({emergency_type})").format(emergency_type=em_type)
            body = t_dict.get("ready_body", "A verified safety destination has been recommended.{dest_details} Tap to view live route.").format(dest_details=dest_details)
        elif notification_type == SafetyNotificationType.ROUTE_UPDATED:
            title = t_dict.get("route_updated_title", "⚠️ Safety Route Updated")
            body = t_dict.get("route_updated_body", "Transit corridor updated due to active conditions.{dest_details} Tap to view latest route.").format(dest_details=dest_details)
        elif notification_type == SafetyNotificationType.DESTINATION_UPDATED:
            title = t_dict.get("dest_updated_title", "📍 Destination Updated")
            body = t_dict.get("dest_updated_body", "Emergency response facility updated based on operational availability.{dest_details} Tap to view.").format(dest_details=dest_details)
        elif notification_type == SafetyNotificationType.ROUTE_UNAVAILABLE:
            title = t_dict.get("route_unsafe_title", "⛔ Route Temporarily Unsafe")
            body = t_dict.get("route_unsafe_body", "Active hazard conditions make transit corridors impassable. Tap to view shelter-in-place instructions.")
        elif notification_type == SafetyNotificationType.HAZARD_WARNING:
            title = t_dict.get("hazard_title", "⚠️ Active Hazard Proximity Alert")
            body = t_dict.get("hazard_body", "An evolving hazard has been detected near your vicinity. Tap to review vital safety precautions.")
        elif notification_type == SafetyNotificationType.EVACUATION_GUIDANCE_APPROVED:
            title = t_dict.get("evac_approved_title", "🛡️ Evacuation Guidance Approved")
            body = t_dict.get("evac_approved_body", "Emergency operations command has approved your evacuation route.{dest_details} Tap to view corridor.").format(dest_details=dest_details)
        elif notification_type == SafetyNotificationType.GUIDANCE_EXPIRED:
            title = t_dict.get("expired_title", "⏱️ Safety Guidance Expired")
            body = t_dict.get("expired_body", "Your previous guidance has expired. Tap to recalculate with real-time operational context.")
        else:  # SAFETY_GUIDANCE_UPDATED
            title = t_dict.get("default_title", "🚨 Emergency Safety Update ({emergency_type})").format(emergency_type=em_type)
            body = t_dict.get("default_body", "Live safety information updated for your report.{dest_details} Tap to view verified guidance.").format(dest_details=dest_details)

        return PushNotificationPayload(
            title=title,
            body=body,
            icon="/favicon.svg",
            badge="/favicon.svg",
            url=f"/safety-guidance/{guidance.secure_access_token}",
            notification_type=notification_type,
            data={
                "guidance_id": guidance.guidance_id,
                "report_id": guidance.report_id,
                "token": guidance.secure_access_token,
                "version": guidance.version,
                "notification_type": notification_type.value,
                "language": lang_code,
            },
        )

    @classmethod
    async def notify_citizen_guidance_update(
        cls,
        guidance: CitizenSafetyGuidance,
        notification_type: SafetyNotificationType = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED,
        event_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> int:
        """
        Notifies all active browser subscriptions associated with the citizen's report
        that new/updated safety guidance is ready, enforcing strict idempotency.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            return 0

        cursor = db["push_subscriptions"].find({
            "report_ids": guidance.report_id,
            "status": PushSubscriptionStatus.ACTIVE.value,
        })

        sent_count = 0
        payload = cls.get_controlled_payload(guidance, notification_type=notification_type)
        resolved_event_id = event_id or guidance.trigger_event_id or f"GEN-{guidance.guidance_id}-v{guidance.version}"

        async for doc in cursor:
            record = cls._doc_to_record(doc)
            
            # Idempotency check: event_id + endpoint + notification_type + guidance_version
            idempotency_raw = f"{resolved_event_id}:{record.endpoint}:{notification_type.value}:{guidance.version}"
            idempotency_key = hashlib.sha256(idempotency_raw.encode("utf-8")).hexdigest()

            existing_delivery = await db["push_deliveries"].find_one({"idempotency_key": idempotency_key})
            if existing_delivery:
                logger.info(f"Skipping duplicate push delivery (Idempotency key: {idempotency_key[:12]}...)")
                continue

            success = await cls.send_web_push(record, payload, db=db)
            if success:
                sent_count += 1
                delivery_record = PushDeliveryRecord(
                    delivery_id=f"DLV-{uuid.uuid4().hex[:10].upper()}",
                    idempotency_key=idempotency_key,
                    event_id=resolved_event_id,
                    recipient_endpoint=record.endpoint,
                    notification_type=notification_type,
                    guidance_version=guidance.version,
                    delivered_at=datetime.now(timezone.utc),
                    status="DELIVERED",
                    provider_status="ACCEPTED_201",
                )
                await db["push_deliveries"].insert_one(delivery_record.model_dump())

        return sent_count

    STATUS_NOTIFICATION_TEMPLATES = {
        "en": {
            "REPORT_ACKNOWLEDGED_TITLE": "Emergency Report Update",
            "REPORT_ACKNOWLEDGED_BODY": "Your emergency report {report_id} has been acknowledged and is now under review.",
            "REPORT_ACCEPTED_TITLE": "Emergency Report Accepted",
            "REPORT_ACCEPTED_BODY": "Your emergency report {report_id} has been accepted and assigned for response coordination.",
            "REPORT_APPROVED_TITLE": "Emergency Report Accepted",
            "REPORT_APPROVED_BODY": "Your emergency report {report_id} has been accepted and assigned for response coordination.",
            "REPORT_REJECTED_TITLE": "Emergency Report Update",
            "REPORT_REJECTED_BODY": "Your emergency report {report_id} has been reviewed and rejected.\n\nReason: {reason}",
        },
        "hi": {
            "REPORT_ACKNOWLEDGED_TITLE": "आपातकालीन रिपोर्ट अपडेट",
            "REPORT_ACKNOWLEDGED_BODY": "आपकी आपातकालीन रिपोर्ट {report_id} स्वीकार कर ली गई है और अब समीक्षाधीन है।",
            "REPORT_ACCEPTED_TITLE": "आपातकालीन रिपोर्ट स्वीकृत",
            "REPORT_ACCEPTED_BODY": "आपकी आपातकालीन रिपोर्ट {report_id} स्वीकृत कर ली गई है और प्रतिक्रिया समन्वय के लिए सौंपी गई है।",
            "REPORT_APPROVED_TITLE": "आपातकालीन रिपोर्ट स्वीकृत",
            "REPORT_APPROVED_BODY": "आपकी आपातकालीन रिपोर्ट {report_id} स्वीकृत कर ली गई है और प्रतिक्रिया समन्वय के लिए सौंपी गई है।",
            "REPORT_REJECTED_TITLE": "आपातकालीन रिपोर्ट अपडेट",
            "REPORT_REJECTED_BODY": "आपकी आपातकालीन रिपोर्ट {report_id} की समीक्षा की गई और अस्वीकार कर दिया गया।\n\nकारण: {reason}",
        },
        "te": {
            "REPORT_ACKNOWLEDGED_TITLE": "అత్యవసర నివేదిక నవీకరణ",
            "REPORT_ACKNOWLEDGED_BODY": "మీ అత్యవసర నివేదిక {report_id} గుర్తించబడింది మరియు ప్రస్తుతం పరిశీలనలో ఉంది.",
            "REPORT_ACCEPTED_TITLE": "అత్యవసర నివేదిక ఆమోదించబడింది",
            "REPORT_ACCEPTED_BODY": "మీ అత్యవసర నివేదిక {report_id} ఆమోదించబడింది మరియు ప్రతిస్పందన సమన్వయానికి కేటాయించబడింది.",
            "REPORT_APPROVED_TITLE": "అత్యవసర నివేదిక ఆమోదించబడింది",
            "REPORT_APPROVED_BODY": "మీ అత్యవసర నివేదిక {report_id} ఆమోదించబడింది మరియు ప్రతిస్పందన సమన్వయానికి కేటాయించబడింది.",
            "REPORT_REJECTED_TITLE": "అత్యవసర నివేదిక నవీకరణ",
            "REPORT_REJECTED_BODY": "మీ అత్యవసర నివేదిక {report_id} సమీక్షించబడింది మరియు తిరస్కరించబడింది.\n\nకారణం: {reason}",
        },
        "ta": {
            "REPORT_ACKNOWLEDGED_TITLE": "அவசர அறிக்கை புதுப்பிப்பு",
            "REPORT_ACKNOWLEDGED_BODY": "உங்கள் அவசர அறிக்கை {report_id} ஏற்றுக்கொள்ளப்பட்டு தற்போது பரிசீலனையில் உள்ளது.",
            "REPORT_ACCEPTED_TITLE": "அவசர அறிக்கை அங்கீகரிக்கப்பட்டது",
            "REPORT_ACCEPTED_BODY": "உங்கள் அவசர அறிக்கை {report_id} அங்கீகரிக்கப்பட்டு நடவடிக்கைக்கு ஒதுக்கப்பட்டுள்ளது.",
            "REPORT_APPROVED_TITLE": "அவசர அறிக்கை அங்கீகரிக்கப்பட்டது",
            "REPORT_APPROVED_BODY": "உங்கள் அவசர அறிக்கை {report_id} அங்கீகரிக்கப்பட்டு நடவடிக்கைக்கு ஒதுக்கப்பட்டுள்ளது.",
            "REPORT_REJECTED_TITLE": "அவசர அறிக்கை புதுப்பிப்பு",
            "REPORT_REJECTED_BODY": "உங்கள் அவசர அறிக்கை {report_id} மதிப்பாய்வு செய்யப்பட்டு நிராகரிக்கப்பட்டது.\n\nகாரணம்: {reason}",
        },
        "kn": {
            "REPORT_ACKNOWLEDGED_TITLE": "ತುರ್ತು ವರದಿ ನವೀಕರಣ",
            "REPORT_ACKNOWLEDGED_BODY": "ನಿಮ್ಮ ತುರ್ತು ವರದಿ {report_id} ಅನ್ನು ಸ್ವೀಕರಿಸಲಾಗಿದೆ ಮತ್ತು ಪ್ರಸ್ತುತ ಪರಿಶೀಲನೆಯಲ್ಲಿದೆ.",
            "REPORT_ACCEPTED_TITLE": "ತುರ್ತು ವರದಿ ಅನುಮೋದಿಸಲಾಗಿದೆ",
            "REPORT_ACCEPTED_BODY": "ನಿಮ್ಮ ತುರ್ತು ವರದಿ {report_id} ಅನ್ನು ಅನುಮೋದಿಸಲಾಗಿದೆ ಮತ್ತು ನಿಯೋಜಿಸಲಾಗಿದೆ.",
            "REPORT_APPROVED_TITLE": "ತುರ್ತು ವರದಿ ಅನುಮೋದಿಸಲಾಗಿದೆ",
            "REPORT_APPROVED_BODY": "ನಿಮ್ಮ ತುರ್ತು ವರದಿ {report_id} ಅನ್ನು ಅನುಮೋದಿಸಲಾಗಿದೆ ಮತ್ತು ನಿಯೋಜಿಸಲಾಗಿದೆ.",
            "REPORT_REJECTED_TITLE": "ತುರ್ತು ವರದಿ ನವೀಕರಣ",
            "REPORT_REJECTED_BODY": "ನಿಮ್ಮ ತುರ್ತು ವರದಿ {report_id} ಅನ್ನು ಪರಿಶೀಲಿಸಲಾಗಿದೆ ಮತ್ತು ತಿರಸ್ಕರಿಸಲಾಗಿದೆ.\n\nಕಾರಣ: {reason}",
        },
    }

    @classmethod
    async def notify_citizen_report_status_update(
        cls,
        report_id: str,
        notification_type: SafetyNotificationType,
        title: str,
        body: str,
        event_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Dict[str, Any]:
        """
        Notifies active browser subscriptions specifically linked to a citizen report_id.
        Accurately differentiates NO_SUBSCRIPTION, DELIVERED, FAILED, and EXPIRED.
        Uses stored citizen language for multilingual localization.
        Never throws unhandled exceptions that could roll back upstream database mutations.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            return {"status": "NO_SUBSCRIPTION", "subscribers_notified": 0, "details": "Database not initialized"}

        clean_id = report_id.strip().upper()

        # Check active subscriptions for this report
        cursor = db["push_subscriptions"].find({
            "report_ids": clean_id,
            "status": PushSubscriptionStatus.ACTIVE.value,
        })
        subscriptions = await cursor.to_list(length=20)

        if not subscriptions:
            # Also check if any active subscription has the report_id without uppercase formatting
            cursor_fallback = db["push_subscriptions"].find({
                "report_ids": report_id.strip(),
                "status": PushSubscriptionStatus.ACTIVE.value,
            })
            subscriptions = await cursor_fallback.to_list(length=20)

        if not subscriptions:
            logger.info(f"No active push subscription found for report {clean_id}. Rejection/status update proceeds.")
            return {
                "status": "NO_SUBSCRIPTION",
                "subscribers_notified": 0,
                "provider_status": "NO_ACTIVE_SUBSCRIPTION",
                "details": f"No active browser push subscription linked to report '{clean_id}'."
            }

        # Check report document for stored citizen language and safety guidance token
        report_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
        url = "/"
        lang_code = "en"
        if report_doc:
            if report_doc.get("safety_guidance_token"):
                url = f"/safety-guidance/{report_doc['safety_guidance_token']}"
            elif report_doc.get("safety_guidance_id"):
                guidance_doc = await db["citizen_safety_guidance"].find_one({"guidance_id": report_doc["safety_guidance_id"]})
                if guidance_doc and guidance_doc.get("secure_access_token"):
                    url = f"/safety-guidance/{guidance_doc['secure_access_token']}"

            lang_field = report_doc.get("language")
            if isinstance(lang_field, dict) and lang_field.get("code"):
                lang_code = str(lang_field["code"]).strip().lower()
            elif report_doc.get("preferred_language"):
                lang_code = str(report_doc["preferred_language"]).strip().lower()

        # Localize title and body based on the report's stored citizen language
        resolved_title = title
        resolved_body = body
        notif_key = notification_type.value if hasattr(notification_type, "value") else str(notification_type)
        tpl_map = cls.STATUS_NOTIFICATION_TEMPLATES.get(lang_code) or cls.STATUS_NOTIFICATION_TEMPLATES.get("en", {})

        reason_val = (data or {}).get("rejection_reason") or (data or {}).get("reason") or (report_doc or {}).get("rejection_reason", "")
        if f"{notif_key}_TITLE" in tpl_map:
            resolved_title = tpl_map[f"{notif_key}_TITLE"]
        if f"{notif_key}_BODY" in tpl_map:
            resolved_body = tpl_map[f"{notif_key}_BODY"].format(report_id=clean_id, reason=reason_val)

        resolved_event_id = event_id or f"EVT-PUSH-{clean_id}-{notif_key}"

        payload_data = {
            "report_id": clean_id,
            "notification_type": notif_key,
            "language": lang_code,
            **(data or {})
        }

        payload = PushNotificationPayload(
            title=resolved_title,
            body=resolved_body,
            icon="/favicon.svg",
            badge="/favicon.svg",
            url=url,
            notification_type=notification_type,
            data=payload_data,
        )

        sent_count = 0
        last_provider_status = None
        has_failed = False

        for sub_doc in subscriptions:
            record = cls._doc_to_record(sub_doc)

            # Idempotency check: event_id + endpoint + notification_type
            idempotency_raw = f"{resolved_event_id}:{record.endpoint}:{notification_type.value}"
            idempotency_key = hashlib.sha256(idempotency_raw.encode("utf-8")).hexdigest()

            existing_delivery = await db["push_deliveries"].find_one({"idempotency_key": idempotency_key})
            if existing_delivery:
                logger.info(f"Skipping duplicate push delivery for {clean_id} (Idempotency key: {idempotency_key[:12]}...)")
                sent_count += 1
                last_provider_status = existing_delivery.get("provider_status", "ACCEPTED_201")
                continue

            try:
                success = await cls.send_web_push(record, payload, db=db)
                if success:
                    sent_count += 1
                    last_provider_status = "ACCEPTED_201"
                    delivery_record = PushDeliveryRecord(
                        delivery_id=f"DLV-{uuid.uuid4().hex[:10].upper()}",
                        idempotency_key=idempotency_key,
                        event_id=resolved_event_id,
                        recipient_endpoint=record.endpoint,
                        notification_type=notification_type,
                        report_id=clean_id,
                        guidance_version=1,
                        delivered_at=datetime.now(timezone.utc),
                        status="DELIVERED",
                        provider_status="ACCEPTED_201",
                    )
                    await db["push_deliveries"].insert_one(delivery_record.model_dump())
                else:
                    has_failed = True
                    # Re-fetch sub to see provider status
                    sub_refresh = await db["push_subscriptions"].find_one({"subscription_id": record.subscription_id})
                    last_provider_status = (sub_refresh or {}).get("last_provider_status", "PROVIDER_FAILED")
            except Exception as push_err:
                logger.warning(f"Error during push notification send for {clean_id}: {push_err}")
                has_failed = True
                last_provider_status = "NETWORK_OR_INTERNAL_ERROR"

        if sent_count > 0:
            return {
                "status": "DELIVERED",
                "subscribers_notified": sent_count,
                "provider_status": last_provider_status or "ACCEPTED_201",
                "details": f"Web push notification delivered to {sent_count} active subscriber(s)."
            }
        else:
            return {
                "status": "FAILED" if has_failed else "NO_SUBSCRIPTION",
                "subscribers_notified": 0,
                "provider_status": last_provider_status or "DELIVERY_FAILED",
                "details": "Push delivery attempt was not accepted by the push service provider."
            }

    @classmethod
    async def get_diagnostic_status(
        cls,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Dict[str, Any]:
        """
        Returns truthful diagnostic status of the Web Push engine.
        Never exposes VAPID private keys or auth secrets.
        """
        cls._init_vapid_keys()
        pub_key = cls.get_public_vapid_key()
        has_priv_key = bool(cls.get_private_vapid_key())
        enabled = bool(settings.WEB_PUSH_ENABLED and pub_key and has_priv_key)

        if db is None:
            db = db_manager.db

        active_count = 0
        total_count = 0
        last_delivery_status = "NONE"
        last_provider_status = "NOT_INITIALIZED"
        last_error = None

        if db is not None:
            active_count = await db["push_subscriptions"].count_documents({"status": "ACTIVE"})
            total_count = await db["push_subscriptions"].count_documents({})

            latest_delivery = await db["push_deliveries"].find_one(
                {},
                sort=[("delivered_at", -1)],
            )
            if latest_delivery:
                last_delivery_status = latest_delivery.get("status", "DELIVERED")
                last_provider_status = latest_delivery.get("provider_status", "ACCEPTED_201")

            latest_failed_sub = await db["push_subscriptions"].find_one(
                {"last_failure_at": {"$ne": None}},
                sort=[("last_failure_at", -1)],
            )
            if latest_failed_sub:
                last_error = latest_failed_sub.get("failure_reason")
                if not latest_delivery or (latest_failed_sub.get("last_failure_at") and latest_delivery.get("delivered_at") and latest_failed_sub["last_failure_at"] > latest_delivery["delivered_at"]):
                    last_delivery_status = "FAILED"
                    last_provider_status = latest_failed_sub.get("last_provider_status", "PROVIDER_ERROR")

        return {
            "enabled": enabled,
            "secure_context_required": True,
            "subscription_registered": active_count > 0,
            "subscription_persisted": total_count > 0,
            "active_subscriptions": active_count,
            "last_delivery_status": last_delivery_status,
            "last_provider_status": last_provider_status,
            "last_error": last_error,
        }

    @staticmethod
    def _doc_to_record(doc: Dict[str, Any]) -> PushSubscriptionRecord:
        raw_status = doc.get("status", "ACTIVE")
        try:
            status_enum = PushSubscriptionStatus(raw_status)
        except Exception:
            status_enum = PushSubscriptionStatus.ACTIVE

        keys_dict = doc.get("keys", {}) if isinstance(doc.get("keys"), dict) else {}
        p256dh_val = doc.get("p256dh") or keys_dict.get("p256dh", "")
        auth_val = doc.get("auth") or keys_dict.get("auth", "")

        return PushSubscriptionRecord(
            subscription_id=doc.get("subscription_id", "SUB-UNKNOWN"),
            endpoint=doc.get("endpoint", ""),
            p256dh=p256dh_val,
            auth=auth_val,
            user_agent=doc.get("user_agent"),
            status=status_enum,
            created_at=doc.get("created_at", datetime.now(timezone.utc)),
            updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
            last_seen_at=doc.get("last_seen_at", datetime.now(timezone.utc)),
            last_success_at=doc.get("last_success_at"),
            last_failure_at=doc.get("last_failure_at"),
            last_provider_status=doc.get("last_provider_status"),
            failure_reason=doc.get("failure_reason"),
            report_ids=doc.get("report_ids", []),
            session_ids=doc.get("session_ids", []),
            subscription_fingerprint=doc.get("subscription_fingerprint", ""),
        )
