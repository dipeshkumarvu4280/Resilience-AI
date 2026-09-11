import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.enums import NotificationDeliveryStatus

logger = logging.getLogger(__name__)


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
        if settings.WHATSAPP_PROVIDER == "mock":
            _active_provider = MockableWhatsAppProvider(
                configured=bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)
            )
        else:
            _active_provider = MetaCloudWhatsAppProvider()
    return _active_provider


def set_whatsapp_provider_override(provider: Optional[WhatsAppProviderInterface]):
    """Allow test fixtures to inject custom/mock providers."""
    global _active_provider
    _active_provider = provider
