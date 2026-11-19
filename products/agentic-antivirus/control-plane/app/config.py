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
        "AAV_PUBLIC_BASE_URL", "https://api.softwareequality.com/apps/agentic-antivirus"))
    oidc_issuer: str = field(default_factory=lambda: os.getenv("AAV_OIDC_ISSUER", ""))
    oidc_client_id: str = field(default_factory=lambda: os.getenv("AAV_OIDC_CLIENT_ID", ""))
    oidc_jwks_url: str = field(default_factory=lambda: os.getenv("AAV_OIDC_JWKS_URL", ""))
    allow_open_registration: bool = field(default_factory=lambda: os.getenv("AAV_OPEN_REGISTRATION", "true") == "true")
    egress_allowlist: tuple = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("AAV_EGRESS_ALLOWLIST", "").split(",") if d.strip()))
    # Outbound mail (verification, password reset, invitations). Empty host = delivery off; mail stays queued.
    # OCI Email Delivery's free allowance is 100 emails a day, so the default daily cap stays under it.
    smtp_host: str = field(default_factory=lambda: os.getenv("AAV_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: _int("AAV_SMTP_PORT", 587))
    smtp_user: str = field(default_factory=lambda: os.getenv("AAV_SMTP_USER", ""))
    smtp_password_file: str = field(default_factory=lambda: os.getenv("AAV_SMTP_PASSWORD_FILE", ""))
    mail_from: str = field(default_factory=lambda: os.getenv("AAV_MAIL_FROM", ""))
    mail_daily_cap: int = field(default_factory=lambda: _int("AAV_MAIL_DAILY_CAP", 90))
    mail_poll_seconds: int = field(default_factory=lambda: _int("AAV_MAIL_POLL_SECONDS", 15))
    # LLM provider chain (llm.py): Claude API when a key and a monthly cap > 0 exist, then a self-hosted
    # Ollama model, then the deterministic rules engine. A zero cap keeps the paid provider off.
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("AAV_ANTHROPIC_API_KEY", ""))
    anthropic_api_key_file: str = field(default_factory=lambda: os.getenv("AAV_ANTHROPIC_API_KEY_FILE", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("AAV_ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    anthropic_base_url: str = field(default_factory=lambda: os.getenv("AAV_ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    # USD per million tokens; set from the provider's current price list (assumption until configured).
    anthropic_price_in: float = field(default_factory=lambda: float(os.getenv("AAV_ANTHROPIC_PRICE_IN_PER_MTOK", "3")))
    anthropic_price_out: float = field(default_factory=lambda: float(os.getenv("AAV_ANTHROPIC_PRICE_OUT_PER_MTOK", "15")))
    llm_monthly_cap_usd: float = field(default_factory=lambda: float(os.getenv("AAV_LLM_MONTHLY_CAP_USD", "0")))
    llm_tenant_monthly_cap_usd: float = field(default_factory=lambda: float(os.getenv("AAV_LLM_TENANT_MONTHLY_CAP_USD", "5")))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("AAV_LLM_TIMEOUT_S", "45")))
    ollama_url: str = field(default_factory=lambda: os.getenv("AAV_OLLAMA_URL", ""))
    ollama_model: str = field(default_factory=lambda: os.getenv("AAV_LLM_LOCAL_MODEL", ""))
    # Defensive harness (§3C): runtime mode for tenants that have not chosen one. A new environment starts in
    # SIMULATION; production sets OBSERVE and enables RESPOND per tenant and cohort. The platform kill switch
    # stops every new response dispatch for all tenants.
    harness_default_mode: str = field(default_factory=lambda: os.getenv("AAV_HARNESS_DEFAULT_MODE", "simulation"))
    harness_kill_switch: bool = field(default_factory=lambda: os.getenv("AAV_HARNESS_KILL_SWITCH", "false") == "true")
    harness_lease_seconds: int = field(default_factory=lambda: _int("AAV_HARNESS_LEASE_SECONDS", 120))
    action_request_ttl_minutes: int = field(default_factory=lambda: _int("AAV_ACTION_REQUEST_TTL_MINUTES", 24 * 60))
    environment: str = field(default_factory=lambda: os.getenv("AAV_ENVIRONMENT", "development"))
    build_sha: str = field(default_factory=lambda: os.getenv("AAV_BUILD_SHA", "unknown"))
    play_package_name: str = field(default_factory=lambda: os.getenv("AAV_PLAY_PACKAGE", "com.equalitysoftware.agenticantivirus"))


settings = Settings()
