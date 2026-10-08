"""SMS provider abstraction for Termii and other providers.

Abstracts the SMS sending logic so the business layer never talks directly
to a provider SDK. The provider can be swapped by changing the class
instantiation without touching the calling code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class SMSResult:
    """Result of an SMS send attempt."""
    succeeded: bool
    provider_reference: str = ''
    cost: int = 0
    error: str = ''


class SMSProvider(ABC):
    """Abstract base for SMS providers."""

    @abstractmethod
    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        """Send an SMS and return a standardized result."""
        pass


class TermiiSMSProvider(SMSProvider):
    """Termii SMS provider implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        sender_id: Optional[str] = None,
        base_url: str = 'https://api.ng.termii.com/api',
    ):
        self.api_key = api_key or getattr(settings, 'TERMII_API_KEY', '')
        self.sender_id = sender_id or getattr(settings, 'TERMII_SENDER_ID', '')
        self.base_url = base_url
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'Content-Type': 'application/json',
            })
        return self._session

    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        """Send an SMS via Termii."""
        if not self.api_key:
            return SMSResult(succeeded=False, error='Termii API key not configured')

        payload = {
            'to': to,
            'sms': message,
            'from': sender_id or self.sender_id,
            'type': 'plain',
            'api_key': self.api_key,
            'channel': 'dnd',
        }

        try:
            import requests
            response = self._get_session().post(
                f'{self.base_url}/sms/send',
                json=payload,
                timeout=10,
            )
            data = response.json()

            if response.status_code == 200 and data.get('message_id'):
                return SMSResult(
                    succeeded=True,
                    provider_reference=data.get('message_id', ''),
                    cost=0,  # Termii doesn't return per-message cost in response
                )
            else:
                error_msg = data.get('message', 'Unknown Termii error')
                return SMSResult(succeeded=False, error=error_msg)

        except Exception as e:
            logger.exception('Termii SMS send failed')
            return SMSResult(succeeded=False, error=str(e))


class ConsoleSMSProvider(SMSProvider):
    """Development/testing provider that logs instead of sending."""

    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        from django.conf import settings
        if not settings.DEBUG:
            return SMSResult(
                succeeded=False,
                error='Console provider only available in DEBUG mode',
            )
        print(f'[SMS] To: {to} | From: {sender_id} | Message: {message}')
        return SMSResult(
            succeeded=True,
            provider_reference=f'console-{timezone.now().timestamp()}',
            cost=0,
        )


def get_sms_provider() -> SMSProvider:
    """Factory to get the configured SMS provider."""
    from django.conf import settings
    provider_name = getattr(settings, 'SMS_PROVIDER', 'console')

    if provider_name == 'termii':
        return TermiiSMSProvider()
    elif provider_name == 'console':
        return ConsoleSMSProvider()
    else:
        # Default to console in development, raise in production
        from django.conf import settings
        if settings.DEBUG:
            return ConsoleSMSProvider()
        raise ValueError(f'Unknown SMS provider: {provider_name}')