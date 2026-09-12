import base64
import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.enums import NotificationDeliveryStatus

logger = logging.getLogger(__name__)


def validate_twilio_signature(
    url: str,
    params: Dict[str, str],
    signature: str,
    auth_token: Optional[str] = None,
) -> bool:
    """
    Validate Twilio webhook request signature (X-Twilio-Signature header).
    Uses standard HMAC-SHA1 signature validation according to Twilio specification.
    """
    token = auth_token or settings.TWILIO_AUTH_TOKEN
    if not token or not signature:
        return False

    # Standard Twilio algorithm: URL + sorted key/value concatenations
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    mac = hmac.new(token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    computed = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(computed, signature)



class WhatsAppDeliveryResult(BaseModel):
    status: NotificationDeliveryStatus
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WhatsAppStatusResult(BaseModel):
    status: NotificationDeliveryStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_status: Optional[str] = None


class WhatsAppProviderInterface(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required provider configuration credentials are present."""
        pass

    @abstractmethod
    async def send_message(
        self,
        recipient_phone: str,
        message: str,
        template_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppDeliveryResult:
        """Send a WhatsApp message to the given recipient."""
        pass

    @abstractmethod
    async def get_delivery_status(self, provider_message_id: str) -> WhatsAppStatusResult:
        """Query delivery status from provider if supported."""
        pass


class MetaCloudWhatsAppProvider(WhatsAppProviderInterface):
    """
    Real WhatsApp Business Cloud API integration using Meta Graph API.
    Does not crash if credentials are not configured; safely returns NOT_CONFIGURED.
    """

    def __init__(
        self,
        api_base_url: Optional[str] = None,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ):
        self.api_base_url = (api_base_url or settings.WHATSAPP_API_BASE_URL).rstrip("/")
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def _clean_phone(self, phone: str) -> str:
        return "".join(c for c in phone if c.isdigit())

    async def send_message(
        self,
        recipient_phone: str,
        message: str,
        template_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppDeliveryResult:
        if not self.is_configured():
            logger.info("WhatsApp delivery skipped: Meta Cloud API credentials not configured.")
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.NOT_CONFIGURED,
                error_code="CREDENTIALS_MISSING",
                error_message="WhatsApp provider credentials (ACCESS_TOKEN / PHONE_NUMBER_ID) are not configured.",
            )

        clean_recipient = self._clean_phone(recipient_phone)
        if not clean_recipient or len(clean_recipient) < 7:
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="INVALID_PHONE_NUMBER",
                error_message="Recipient phone number is invalid or empty.",
            )

        url = f"{self.api_base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Build payload
        if template_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_recipient,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en_US"},
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_recipient,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message,
                },
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (200, 201):
                    res_data = response.json()
                    msg_id = None
                    if "messages" in res_data and len(res_data["messages"]) > 0:
                        msg_id = res_data["messages"][0].get("id")
                    return WhatsAppDeliveryResult(
                        status=NotificationDeliveryStatus.SENT,
                        provider_message_id=msg_id,
                    )
                else:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("error", {}).get("message", response.text)
                        err_code = str(err_json.get("error", {}).get("code", response.status_code))
                    except Exception:
                        err_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                        err_code = str(response.status_code)

                    logger.warning("WhatsApp API delivery error: code=%s msg=%s", err_code, err_msg)
                    return WhatsAppDeliveryResult(
                        status=NotificationDeliveryStatus.FAILED,
                        error_code=err_code,
                        error_message=err_msg,
                    )
        except httpx.TimeoutException:
            logger.warning("WhatsApp API delivery timed out.")
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="TIMEOUT",
                error_message="WhatsApp provider request timed out after 10.0s.",
            )
        except Exception as ex:
            logger.error("WhatsApp delivery exception: %s", str(ex), exc_info=True)
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="EXCEPTION",
                error_message=str(ex),
            )

    async def get_delivery_status(self, provider_message_id: str) -> WhatsAppStatusResult:
        if not self.is_configured():
            return WhatsAppStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)
        # Graph API message status is usually pushed via Webhook, but query endpoint can be checked
        return WhatsAppStatusResult(status=NotificationDeliveryStatus.SENT)


class TwilioWhatsAppProvider(WhatsAppProviderInterface):
    """
    Official Twilio WhatsApp Sandbox / Production Provider.
    Implements Twilio REST Messages API asynchronously via httpx.
    Normalizes numbers to 'whatsapp:+<E.164>' format and maps Twilio delivery states.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        enabled: Optional[bool] = None,
        status_callback_url: Optional[str] = None,
    ):
        self.account_sid = account_sid if account_sid is not None else settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token if auth_token is not None else settings.TWILIO_AUTH_TOKEN
        self.from_number = from_number if from_number is not None else (settings.TWILIO_WHATSAPP_FROM or "whatsapp:+14155238886")
        self.enabled = enabled if enabled is not None else settings.TWILIO_WHATSAPP_ENABLED
        self.status_callback_url = status_callback_url if status_callback_url is not None else settings.TWILIO_WHATSAPP_STATUS_CALLBACK_URL
        self.api_base_url = "https://api.twilio.com/2010-04-01"

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.enabled)

    def normalize_recipient(self, phone: str) -> Optional[str]:
        """
        Normalize a phone string into a valid Twilio WhatsApp address (whatsapp:+<digits>).
        Accepts: '9801338643', '+919801338643', 'whatsapp:+919801338643', '919801338643'.
        """
        if not phone:
            return None
        cleaned = phone.strip()
        if cleaned.startswith("whatsapp:"):
            cleaned = cleaned[9:].strip()

        has_plus = cleaned.startswith("+")
        digits = "".join(c for c in cleaned if c.isdigit())

        if len(digits) < 7:
            return None

        # If 10 digits without country code (standard Indian mobile format), default to +91
        if len(digits) == 10 and not has_plus:
            digits = f"91{digits}"

        return f"whatsapp:+{digits}"

    async def send_message(
        self,
        recipient_phone: str,
        message: str,
        template_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppDeliveryResult:
        if not self.is_configured():
            logger.info("Twilio WhatsApp delivery skipped: credentials not configured or TWILIO_WHATSAPP_ENABLED is False.")
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.NOT_CONFIGURED,
                error_code="CREDENTIALS_MISSING",
                error_message="Twilio provider credentials (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN) not configured or disabled.",
            )

        norm_recipient = self.normalize_recipient(recipient_phone)
        if not norm_recipient:
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="INVALID_PHONE_NUMBER",
                error_message=f"Recipient phone number '{recipient_phone}' could not be normalized to a valid WhatsApp address.",
            )

        from_formatted = self.from_number
        if not from_formatted.startswith("whatsapp:"):
            from_formatted = f"whatsapp:{from_formatted}"

        url = f"{self.api_base_url}/Accounts/{self.account_sid}/Messages.json"

        form_data = {
            "From": from_formatted,
            "To": norm_recipient,
            "Body": message,
        }
        if self.status_callback_url:
            form_data["StatusCallback"] = self.status_callback_url

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(
                    url,
                    data=form_data,
                    auth=(self.account_sid, self.auth_token),
                )

                if response.status_code in (200, 201):
                    res_data = response.json()
                    msg_sid = res_data.get("sid")
                    twilio_status = (res_data.get("status") or "queued").lower()

                    status_map = {
                        "queued": NotificationDeliveryStatus.QUEUED,
                        "sending": NotificationDeliveryStatus.SENDING,
                        "sent": NotificationDeliveryStatus.SENT,
                        "delivered": NotificationDeliveryStatus.DELIVERED,
                        "read": NotificationDeliveryStatus.READ,
                        "failed": NotificationDeliveryStatus.FAILED,
                        "undelivered": NotificationDeliveryStatus.FAILED,
                    }
                    mapped_status = status_map.get(twilio_status, NotificationDeliveryStatus.QUEUED)

                    return WhatsAppDeliveryResult(
                        status=mapped_status,
                        provider_message_id=msg_sid,
                    )
                else:
                    try:
                        err_json = response.json()
                        err_code = str(err_json.get("code") or response.status_code)
                        err_msg = err_json.get("message") or response.text
                    except Exception:
                        err_code = str(response.status_code)
                        err_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                    logger.warning("Twilio WhatsApp API error: code=%s msg=%s", err_code, err_msg)
                    return WhatsAppDeliveryResult(
                        status=NotificationDeliveryStatus.FAILED,
                        error_code=err_code,
                        error_message=err_msg,
                    )

        except httpx.TimeoutException:
            logger.warning("Twilio WhatsApp API request timed out.")
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="TIMEOUT",
                error_message="Twilio WhatsApp API request timed out after 12.0s.",
            )
        except Exception as ex:
            logger.error("Twilio WhatsApp delivery exception: %s", str(ex), exc_info=True)
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="EXCEPTION",
                error_message=str(ex),
            )

    async def get_delivery_status(self, provider_message_id: str) -> WhatsAppStatusResult:
        if not self.is_configured() or not provider_message_id:
            return WhatsAppStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)

        url = f"{self.api_base_url}/Accounts/{self.account_sid}/Messages/{provider_message_id}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, auth=(self.account_sid, self.auth_token))
                if res.status_code == 200:
                    data = res.json()
                    st = (data.get("status") or "").lower()
                    status_map = {
                        "queued": NotificationDeliveryStatus.QUEUED,
                        "sending": NotificationDeliveryStatus.SENDING,
                        "sent": NotificationDeliveryStatus.SENT,
                        "delivered": NotificationDeliveryStatus.DELIVERED,
                        "read": NotificationDeliveryStatus.READ,
                        "failed": NotificationDeliveryStatus.FAILED,
                        "undelivered": NotificationDeliveryStatus.FAILED,
                    }
                    return WhatsAppStatusResult(
                        status=status_map.get(st, NotificationDeliveryStatus.SENT),
                        raw_status=st,
                    )
        except Exception as ex:
            logger.warning("Failed to query Twilio status for %s: %s", provider_message_id, str(ex))

        return WhatsAppStatusResult(status=NotificationDeliveryStatus.SENT)


class DisabledWhatsAppProvider(WhatsAppProviderInterface):
    """Provider when WhatsApp channel is explicitly disabled."""

    def is_configured(self) -> bool:
        return False

    async def send_message(
        self,
        recipient_phone: str,
        message: str,
        template_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppDeliveryResult:
        return WhatsAppDeliveryResult(
            status=NotificationDeliveryStatus.NOT_CONFIGURED,
            error_code="DISABLED",
            error_message="WhatsApp notifications are disabled by configuration.",
        )

    async def get_delivery_status(self, provider_message_id: str) -> WhatsAppStatusResult:
        return WhatsAppStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)


class MockableWhatsAppProvider(WhatsAppProviderInterface):
    """
    Deterministic provider for automated testing and local development testing.
    Can be configured to succeed, fail, or simulate missing credentials.
    """

    def __init__(self, configured: bool = True, should_succeed: bool = True, error_msg: Optional[str] = None):
        self._configured = configured
        self._should_succeed = should_succeed
        self._error_msg = error_msg or "Mock delivery failed"
        self.sent_messages = []

    def is_configured(self) -> bool:
        return self._configured

    async def send_message(
        self,
        recipient_phone: str,
        message: str,
        template_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppDeliveryResult:
        if not self._configured:
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.NOT_CONFIGURED,
                error_code="CREDENTIALS_MISSING",
                error_message="WhatsApp credentials not configured.",
            )

        if not recipient_phone or len(recipient_phone) < 7:
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="INVALID_PHONE_NUMBER",
                error_message="Invalid recipient phone number.",
            )

        if not self._should_succeed:
            return WhatsAppDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="PROVIDER_ERROR",
                error_message=self._error_msg,
            )

        msg_id = f"wamid.mock_{int(datetime.now(timezone.utc).timestamp()*1000)}"
        self.sent_messages.append({
            "recipient_phone": recipient_phone,
            "message": message,
            "message_id": msg_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return WhatsAppDeliveryResult(
            status=NotificationDeliveryStatus.SENT,
            provider_message_id=msg_id,
        )

    async def get_delivery_status(self, provider_message_id: str) -> WhatsAppStatusResult:
        if not self._configured:
            return WhatsAppStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)
        return WhatsAppStatusResult(status=NotificationDeliveryStatus.DELIVERED)


# Singleton / Factory
_active_provider: Optional[WhatsAppProviderInterface] = None


def get_whatsapp_provider() -> WhatsAppProviderInterface:
    global _active_provider
    if _active_provider is None:
        provider_name = (settings.WHATSAPP_PROVIDER or "meta_cloud").strip().lower()
        if provider_name == "mock":
            _active_provider = MockableWhatsAppProvider(
                configured=bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)
            )
        elif provider_name == "twilio":
            _active_provider = TwilioWhatsAppProvider()
        elif provider_name in ("disabled", "off", "none"):
            _active_provider = DisabledWhatsAppProvider()
        else:  # "meta" or "meta_cloud" (default)
            _active_provider = MetaCloudWhatsAppProvider()
    return _active_provider


def set_whatsapp_provider_override(provider: Optional[WhatsAppProviderInterface]):
    """Allow test fixtures to inject custom/mock providers."""
    global _active_provider
    _active_provider = provider
