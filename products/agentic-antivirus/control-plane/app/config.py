"""Runtime configuration. Secrets come from the environment or mounted files (BE-09), never git."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv(
        "AAV_DATABASE_URL", "postgresql://aav_app@localhost:5432/aav"))
    signing_key_file: str = field(default_factory=lambda: os.getenv("AAV_SIGNING_KEY_FILE", ""))
    governance_url: str = field(default_factory=lambda: os.getenv("AAV_GOVERNANCE_URL", ""))
    governance_timeout_s: float = field(default_factory=lambda: float(os.getenv("AAV_GOVERNANCE_TIMEOUT_S", "3")))
    aepx_bus_url: str = field(default_factory=lambda: os.getenv("AAV_AEPX_BUS_URL", ""))  # opt-in LLM via AEP-X bus
    file_store_dir: str = field(default_factory=lambda: os.getenv("AAV_FILE_STORE_DIR", "/var/lib/aav/files"))
    max_upload_bytes: int = field(default_factory=lambda: _int("AAV_MAX_UPLOAD_BYTES", 100 * 1024 * 1024))
    tenant_quota_bytes: int = field(default_factory=lambda: _int("AAV_TENANT_QUOTA_BYTES", 2 * 1024 * 1024 * 1024))
    session_hours: int = field(default_factory=lambda: _int("AAV_SESSION_HOURS", 12))
    approval_ttl_minutes: int = field(default_factory=lambda: _int("AAV_APPROVAL_TTL_MINUTES", 60))
    command_ttl_minutes: int = field(default_factory=lambda: _int("AAV_COMMAND_TTL_MINUTES", 60))
    public_base_url: str = field(default_factory=lambda: os.getenv(
        "AAV_PUBLIC_BASE_URL", "https://softwareequality.com/apps/agentic-antivirus"))
    oidc_issuer: str = field(default_factory=lambda: os.getenv("AAV_OIDC_ISSUER", ""))
    oidc_client_id: str = field(default_factory=lambda: os.getenv("AAV_OIDC_CLIENT_ID", ""))
    oidc_jwks_url: str = field(default_factory=lambda: os.getenv("AAV_OIDC_JWKS_URL", ""))
    allow_open_registration: bool = field(default_factory=lambda: os.getenv("AAV_OPEN_REGISTRATION", "true") == "true")
    egress_allowlist: tuple = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("AAV_EGRESS_ALLOWLIST", "").split(",") if d.strip()))
    play_package_name: str = field(default_factory=lambda: os.getenv("AAV_PLAY_PACKAGE", "com.equalitysoftware.agenticantivirus"))


settings = Settings()
