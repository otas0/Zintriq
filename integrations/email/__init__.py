"""Email provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    slug: str = "none"

    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> bool:
        pass


class NullEmailProvider(EmailProvider):
    slug = "none"

    def is_configured(self) -> bool:
        return False

    def send(self, *, to: str, subject: str, body: str) -> bool:
        return False


def get_email_provider(name: str | None = None) -> EmailProvider:
    from integrations.config import email_provider_name
    slug = (name or email_provider_name()).lower()
    if slug in ("none", ""):
        return NullEmailProvider()
    return NullEmailProvider()  # future: SendGrid, Postmark, etc.


class EmailService:
    @staticmethod
    def provider():
        return get_email_provider()

    @staticmethod
    def send(*, to: str, subject: str, body: str) -> bool:
        provider = get_email_provider()
        if not provider.is_configured():
            return False
        return provider.send(to=to, subject=subject, body=body)
