import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.enums import NotificationDeliveryStatus

logger = logging.getLogger(__name__)


def normalize_phone_e164(phone: str) -> Optional[str]:
    """
    Authoritative phone normalization into strict E.164 format (+<country_code><national_number>).
    Accepts: '9801338643', '+919801338643', '+14155552671', '919801338643', ' (415) 555-2671 '.
    Returns None if number is invalid, empty, or too short (<7 digits).
    """
    if not phone:
        return None

    cleaned = str(phone).strip()
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[9:].strip()

    has_plus = cleaned.startswith("+")
    digits = "".join(c for c in cleaned if c.isdigit())

    if len(digits) < 7:
        return None

    # If 10 digits without leading + (standard Indian mobile format), default to +91
    if len(digits) == 10 and not has_plus:
        return f"+91{digits}"

    # If already had plus or standard full digits with country code
    return f"+{digits}"



class SmsDeliveryResult(BaseModel):
    status: NotificationDeliveryStatus
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SmsStatusResult(BaseModel):
    status: NotificationDeliveryStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_status: Optional[str] = None


class SmsProviderInterface(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required provider credentials and sender are configured and enabled."""
        pass

    @abstractmethod
    async def send_sms(
        self,
        recipient_phone: str,
        message: str,
    ) -> SmsDeliveryResult:
        """Send an SMS to the given recipient."""
        pass

    @abstractmethod
    async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
        """Query delivery status from provider if supported."""
        pass


class TwilioSmsProvider(SmsProviderInterface):
    """
    Official Twilio SMS Provider.
    Implements Twilio REST Messages API asynchronously via httpx.
    Supports both 'trial_template' mode (Twilio predefined trial templates like 'sms_internal_alerts')
    and 'custom' mode (free-form body for production/paid accounts).
    Normalizes numbers to E.164 format (+<digits>) and maps Twilio delivery states.
    Never exposes credentials or Auth Token in errors or logs.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        enabled: Optional[bool] = None,
        status_callback_url: Optional[str] = None,
        mode: Optional[str] = None,
        trial_template: Optional[str] = None,
    ):
        self.account_sid = account_sid if account_sid is not None else settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token if auth_token is not None else settings.TWILIO_AUTH_TOKEN
        self.from_number = from_number if from_number is not None else settings.TWILIO_SMS_FROM
        self.enabled = enabled if enabled is not None else settings.TWILIO_SMS_ENABLED
        self.status_callback_url = status_callback_url if status_callback_url is not None else settings.TWILIO_SMS_STATUS_CALLBACK_URL
        self.mode = (mode if mode is not None else getattr(settings, "TWILIO_SMS_MODE", "trial_template")).lower().strip()
        self.trial_template = trial_template if trial_template is not None else getattr(settings, "TWILIO_SMS_TRIAL_TEMPLATE", "sms_internal_alerts")
        self.api_base_url = "https://api.twilio.com/2010-04-01"

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number and self.enabled)

    def normalize_recipient(self, phone: str) -> Optional[str]:
        return normalize_phone_e164(phone)

    async def send_sms(
        self,
        recipient_phone: str,
        message: str,
    ) -> SmsDeliveryResult:
        if not self.is_configured():
            logger.info("Twilio SMS delivery skipped: credentials/sender not configured or TWILIO_SMS_ENABLED is False.")
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.NOT_CONFIGURED,
                error_code="CREDENTIALS_MISSING",
                error_message="Twilio SMS provider credentials (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_SMS_FROM) not configured or disabled.",
            )

        norm_recipient = self.normalize_recipient(recipient_phone)
        if not norm_recipient:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="INVALID_PHONE_NUMBER",
                error_message=f"Recipient phone number '{recipient_phone}' could not be normalized to valid E.164.",
            )

        # Normalize sender number
        from_norm = normalize_phone_e164(self.from_number) or self.from_number

        # Trial Template Adapter:
        # In 'trial_template' mode, use Twilio's approved predefined template keyword.
        # In 'custom' mode, send the full application-generated emergency text.
        if self.mode == "trial_template":
            body_to_send = self.trial_template
        else:
            body_to_send = message

        url = f"{self.api_base_url}/Accounts/{self.account_sid}/Messages.json"

        form_data = {
            "From": from_norm,
            "To": norm_recipient,
            "Body": body_to_send,
        }
        if self.status_callback_url:
            form_data["StatusCallback"] = self.status_callback_url

        masked_to = f"{norm_recipient[:3]}***{norm_recipient[-3:]}" if len(norm_recipient) >= 6 else "***"
        masked_sid = f"...{self.account_sid[-4:]}" if self.account_sid else "None"

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

                    if not msg_sid or not str(msg_sid).startswith("SM"):
                        logger.error("Twilio accepted response missing valid Message SID: %s", res_data)
                        return SmsDeliveryResult(
                            status=NotificationDeliveryStatus.FAILED,
                            error_code="NO_MESSAGE_SID",
                            error_message="Twilio response did not contain a valid Message SID.",
                        )

                    status_map = {
                        "queued": NotificationDeliveryStatus.QUEUED,
                        "accepted": NotificationDeliveryStatus.QUEUED,
                        "sending": NotificationDeliveryStatus.SENDING,
                        "sent": NotificationDeliveryStatus.SENT,
                        "delivered": NotificationDeliveryStatus.DELIVERED,
                        "undelivered": NotificationDeliveryStatus.UNDELIVERED,
                        "failed": NotificationDeliveryStatus.FAILED,
                    }
                    mapped_status = status_map.get(twilio_status, NotificationDeliveryStatus.QUEUED)

                    logger.info(
                        "Twilio SMS accepted: to=%s msg_sid=%s status=%s mode=%s",
                        masked_to,
                        msg_sid,
                        mapped_status.value,
                        self.mode,
                    )

                    return SmsDeliveryResult(
                        status=mapped_status,
                        provider_message_id=msg_sid,
                    )
                else:
                    try:
                        err_json = response.json()
                        raw_code = str(err_json.get("code") or response.status_code)
                        err_msg = err_json.get("message") or response.text
                    except Exception:
                        raw_code = str(response.status_code)
                        err_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                    # Precise Error Classification
                    if raw_code == "572002" or "verified recipient" in err_msg.lower():
                        err_code = "572002"
                        err_classification = "TRIAL_RECIPIENT_NOT_VERIFIED"
                    elif raw_code == "572006" or "invalid template" in err_msg.lower():
                        err_code = "572006"
                        err_classification = "TRIAL_TEMPLATE_REJECTED"
                    elif 400 <= response.status_code < 500:
                        err_code = raw_code
                        err_classification = "PROVIDER_REJECTED"
                    else:
                        err_code = raw_code
                        err_classification = "PROVIDER_ERROR"

                    logger.warning(
                        "Twilio SMS API rejection [%s]: to=%s code=%s msg=%s (Account: %s)",
                        err_classification,
                        masked_to,
                        err_code,
                        err_msg,
                        masked_sid,
                    )
                    return SmsDeliveryResult(
                        status=NotificationDeliveryStatus.FAILED,
                        error_code=err_code,
                        error_message=err_msg,
                    )

        except httpx.TimeoutException:
            logger.warning("Twilio SMS API request timed out for to=%s", masked_to)
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="TIMEOUT",
                error_message="Twilio SMS API request timed out after 12.0s.",
            )
        except Exception as ex:
            logger.error("Twilio SMS delivery exception: %s", str(ex), exc_info=True)
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="EXCEPTION",
                error_message=str(ex),
            )

    async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
        if not self.is_configured() or not provider_message_id:
            return SmsStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)

        url = f"{self.api_base_url}/Accounts/{self.account_sid}/Messages/{provider_message_id}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, auth=(self.account_sid, self.auth_token))
                if res.status_code == 200:
                    data = res.json()
                    st = (data.get("status") or "").lower()
                    status_map = {
                        "queued": NotificationDeliveryStatus.QUEUED,
                        "accepted": NotificationDeliveryStatus.QUEUED,
                        "sending": NotificationDeliveryStatus.SENDING,
                        "sent": NotificationDeliveryStatus.SENT,
                        "delivered": NotificationDeliveryStatus.DELIVERED,
                        "undelivered": NotificationDeliveryStatus.UNDELIVERED,
                        "failed": NotificationDeliveryStatus.FAILED,
                    }
                    return SmsStatusResult(
                        status=status_map.get(st, NotificationDeliveryStatus.SENT),
                        raw_status=st,
                    )
        except Exception as ex:
            logger.warning("Failed to query Twilio SMS status for %s: %s", provider_message_id, str(ex))

        return SmsStatusResult(status=NotificationDeliveryStatus.SENT)


class DisabledSmsProvider(SmsProviderInterface):
    """Provider when SMS channel is explicitly disabled."""

    def is_configured(self) -> bool:
        return False

    async def send_sms(
        self,
        recipient_phone: str,
        message: str,
    ) -> SmsDeliveryResult:
        return SmsDeliveryResult(
            status=NotificationDeliveryStatus.NOT_CONFIGURED,
            error_code="DISABLED",
            error_message="SMS notifications are disabled by configuration.",
        )

    async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
        return SmsStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)


class MockableSmsProvider(SmsProviderInterface):
    """Deterministic SMS provider for testing without external network calls."""

    def __init__(self, configured: bool = True, should_succeed: bool = True, error_msg: Optional[str] = None):
        self._configured = configured
        self._should_succeed = should_succeed
        self._error_msg = error_msg or "Mock SMS delivery failed"
        self.sent_messages = []

    def is_configured(self) -> bool:
        return self._configured

    async def send_sms(
        self,
        recipient_phone: str,
        message: str,
    ) -> SmsDeliveryResult:
        if not self._configured:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.NOT_CONFIGURED,
                error_code="CREDENTIALS_MISSING",
                error_message="SMS credentials not configured.",
            )

        norm = normalize_phone_e164(recipient_phone)
        if not norm:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="INVALID_PHONE_NUMBER",
                error_message=f"Invalid recipient phone number '{recipient_phone}'.",
            )

        if not self._should_succeed:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="PROVIDER_ERROR",
                error_message=self._error_msg,
            )

        msg_sid = f"SMmock_{int(datetime.now(timezone.utc).timestamp()*1000)}"
        self.sent_messages.append({
            "recipient_phone": norm,
            "message": message,
            "message_sid": msg_sid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return SmsDeliveryResult(
            status=NotificationDeliveryStatus.SENT,
            provider_message_id=msg_sid,
        )

    async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
        if not self._configured:
            return SmsStatusResult(status=NotificationDeliveryStatus.NOT_CONFIGURED)
        return SmsStatusResult(status=NotificationDeliveryStatus.DELIVERED)


# Singleton / Factory
_active_sms_provider: Optional[SmsProviderInterface] = None


def get_sms_provider() -> SmsProviderInterface:
    global _active_sms_provider
    if _active_sms_provider is None:
        provider_name = (settings.SMS_PROVIDER or "disabled").strip().lower()
        if provider_name == "mock":
            _active_sms_provider = MockableSmsProvider(
                configured=bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_SMS_FROM)
            )
        elif provider_name == "twilio":
            _active_sms_provider = TwilioSmsProvider()
        else:  # "disabled", "none", "off"
            _active_sms_provider = DisabledSmsProvider()
    return _active_sms_provider


def set_sms_provider_override(provider: Optional[SmsProviderInterface]):
    """Allow test fixtures to inject custom/mock SMS providers."""
    global _active_sms_provider
    _active_sms_provider = provider
