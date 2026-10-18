"""Compiled instantiation artifact (host-independent)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from meta.instantiation.errors import InstantiationError

# Host public surface for software.page. Not a filesystem path.
WEB_BUILD_PREFIX = "/build/"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

TARGET_DESC = "desc"
TARGET_WEB_BUILD = "web_build"
TARGET_UIR = "uir"
TARGET_VISUAL = "visual"
TARGET_DEVICE = "device"
TARGET_OS_HOST = "os_host"
TARGET_CANVAS = "canvas"
TARGET_DESKTOP_HOST = "desktop_host"
KNOWN_TARGETS = frozenset(
    {
        TARGET_DESC,
        TARGET_WEB_BUILD,
        TARGET_UIR,
        TARGET_VISUAL,
        TARGET_DEVICE,
        TARGET_OS_HOST,
        TARGET_CANVAS,
        TARGET_DESKTOP_HOST,
    }
)


def validate_slug(slug: str | None) -> str:
    value = str(slug or "").strip()
    if not value or not SLUG_RE.fullmatch(value):
        raise InstantiationError(
            "slug must be 1–64 lowercase letters, digits, and inner hyphens"
        )
    return value


def public_url_for_slug(slug: str) -> str:
    return f"{WEB_BUILD_PREFIX}{validate_slug(slug)}"


def checksum_payload(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Artifact:
    target: str
    boundary_id: str
    media_type: str
    payload: str
    checksum: str
    public_url: str | None = None
    slug: str | None = None

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "boundary_id": self.boundary_id,
            "checksum": self.checksum,
            "media_type": self.media_type,
            "payload": self.payload,
            "target": self.target,
        }
        if self.public_url is not None:
            out["public_url"] = self.public_url
        if self.slug is not None:
            out["slug"] = self.slug
        return out

    def payload_object(self) -> Any:
        if self.media_type != "application/json":
            raise InstantiationError("payload is not JSON")
        try:
            return json.loads(self.payload)
        except json.JSONDecodeError as exc:
            raise InstantiationError(f"artifact payload is not JSON: {exc}") from exc

    @staticmethod
    def from_data(data: dict[str, Any]) -> Artifact:
        if not isinstance(data, dict):
            raise InstantiationError("artifact must be an object")
        payload = data.get("payload")
        if not isinstance(payload, str):
            raise InstantiationError("artifact payload must be a string")
        checksum = str(data.get("checksum") or "")
        expected = checksum_payload(payload)
        if checksum != expected:
            raise InstantiationError("artifact checksum mismatch")
        slug = data.get("slug")
        public_url = data.get("public_url")
        return Artifact(
            target=str(data.get("target") or ""),
            boundary_id=str(data.get("boundary_id") or ""),
            media_type=str(data.get("media_type") or "application/json"),
            payload=payload,
            checksum=checksum,
            public_url=None if public_url is None else str(public_url),
            slug=None if slug is None else str(slug),
        )
