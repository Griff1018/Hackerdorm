"""Settings loaded from environment variables, with a .env file as fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

SERVICE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def _bool(name: str, default: bool = True) -> bool:
    """Truthy unless explicitly set to a falsey token. Empty/missing keeps the default."""
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value not in ("0", "false", "no", "off")


# The platform injects the real public host of the running service into one of these.
# Reading it beats a hard-coded PUBLIC_BASE_URL, because the share link changes on
# every redeploy and a stale value would point the Telegram webhook at a dead URL.
_HOST_ENV_KEYS = (
    "PUBLIC_HOST",
    "PUBLIC_HOSTNAME",
    "PUBLIC_URL",
    "APP_URL",
    "APP_HOST",
    "SERVICE_URL",
    "SANDBOX_URL",
    "VIRTUAL_HOST",
    "EXTERNAL_URL",
    "RENDER_EXTERNAL_URL",
)


def _detect_public_base_url() -> str:
    """Best-effort discovery of this service's own public https URL at startup.

    Order of preference:
      1. An explicit PUBLIC_BASE_URL, but only if it looks like a live deployment host.
      2. A platform-injected host env var.
    Returns "" when nothing usable is found, in which case the caller falls back
    to Telegram long polling instead of registering a webhook."""
    def usable(url: str) -> bool:
        host = url.split("://", 1)[-1].split("/", 1)[0].lower()
        if not host or "localhost" in host or host.startswith(("127.", "0.0.0.0")):
            return False
        # Avoid container names / internal service names such as HOSTNAME=abc123.
        return "." in host

    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    # A loopback/localhost value is a dev leftover — useless once deployed, so ignore it.
    if explicit and usable(explicit):
        return explicit
    for key in _HOST_ENV_KEYS:
        raw = os.environ.get(key, "").strip().rstrip("/")
        if not raw:
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            url = raw
        else:
            url = f"https://{raw}"
        if not usable(url):
            continue
        return url
    return ""



@dataclass
class Settings:
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    admin_chat_ids: list[str] = field(default_factory=list)
    telegram_webhook_secret: str = ""
    public_base_url: str = ""
    # Master switches for the two intake channels. Set to "0" to disable that trigger
    # entirely (no webhook registration, no inbound polling) while keeping the web
    # dashboard, website enquiry form and schedulers running.
    telegram_intake_enabled: bool = True
    gmail_intake_enabled: bool = True

    gmail_address: str = ""
    gmail_app_password: str = ""
    imap_host: str = "imap.gmail.com"
    imap_folder: str = "INBOX"
    imap_poll_seconds: int = 60
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    mail_from_name: str = "Alex"
    listing_senders: list[str] = field(default_factory=list)
    alert_emails: list[str] = field(default_factory=list)
    dossier_emails: list[str] = field(default_factory=list)

    llm_api_key: str = ""
    llm_base_url: str = "https://tokenhub.tencentmaas.com/v1"
    llm_model_chat: str = "hy3"
    llm_model_task: str = "hy3"
    llm_reasoning_effort: str = "low"

    firecrawl_api_key: str = ""

    timezone: str = "Australia/Sydney"
    reply_debounce_seconds: int = 10
    reengagement_hour: int = 9
    briefing_hour: int = 8
    followup_schedule_days: list[int] = field(default_factory=lambda: [3, 5, 7, 30, 90])
    hot_lead_score: int = 6
    cron_secret: str = ""
    support_contact: str = ""
    admin_dashboard_key: str = ""

    # --- cloud service (WorkBuddy cloud-sdk equivalent for this Python backend) ---
    # Populated from publicConfig after `workbuddy_cloud_service` activation succeeds.
    cloud_endpoint: str = ""            # publicConfig.endpoint
    cloud_publishable_key: str = ""     # publicConfig.publishableKey
    cloud_oauth_relay: str = ""        # publicConfig.oauthRelayBaseUrl
    cloud_admin_email: str = ""        # agent's cloud Auth account (email+password login)
    cloud_admin_password: str = ""

    data_dir: Path = SERVICE_DIR / "data"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def use_cloud(self) -> bool:
        """True only when cloud publicConfig is present. Gates every cloud code path so the
        app keeps running on local SQLite/Hunyuan when cloud is not activated or disabled."""
        return bool(self.cloud_endpoint and self.cloud_publishable_key)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "property_agent.db"

    @property
    def contracts_dir(self) -> Path:
        return self.data_dir / "contracts"

    @property
    def telegram_enabled(self) -> bool:
        """Telegram intake is active only when a token exists AND the channel is switched on."""
        return bool(self.telegram_bot_token) and self.telegram_intake_enabled

    @property
    def mail_enabled(self) -> bool:
        """Inbound Gmail polling is active only when creds exist AND the channel is switched on.
        Outbound email (SMTP) is unaffected by this switch — see `smtp_enabled`."""
        return bool(self.gmail_address and self.gmail_app_password) and self.gmail_intake_enabled

    @property
    def smtp_enabled(self) -> bool:
        """Outbound email can be sent whenever SMTP credentials exist, regardless of whether
        inbound Gmail polling is switched off. Website enquiries and lead replies depend on this."""
        return bool(self.gmail_address and self.gmail_app_password)

    def is_admin(self, chat_id: int | str) -> bool:
        return str(chat_id) in self.admin_chat_ids


def load_settings() -> Settings:
    _load_dotenv(SERVICE_DIR / ".env")
    env = os.environ.get
    data_dir = Path(env("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = SERVICE_DIR / data_dir
    schedule = _list("FOLLOWUP_SCHEDULE_DAYS")
    return Settings(
        telegram_bot_token=env("TELEGRAM_BOT_TOKEN", ""),
        telegram_bot_username=env("TELEGRAM_BOT_USERNAME", "").lstrip("@"),
        admin_chat_ids=_list("ADMIN_CHAT_IDS"),
        telegram_webhook_secret=env("TELEGRAM_WEBHOOK_SECRET", ""),
        public_base_url=_detect_public_base_url(),
        telegram_intake_enabled=_bool("TELEGRAM_INTAKE_ENABLED", True),
        gmail_intake_enabled=_bool("GMAIL_INTAKE_ENABLED", True),
        gmail_address=env("GMAIL_ADDRESS", ""),
        gmail_app_password=env("GMAIL_APP_PASSWORD", "").replace(" ", ""),
        imap_host=env("IMAP_HOST", "imap.gmail.com"),
        imap_folder=env("IMAP_FOLDER", "INBOX"),
        imap_poll_seconds=_int("IMAP_POLL_SECONDS", 60),
        smtp_host=env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_int("SMTP_PORT", 465),
        mail_from_name=env("MAIL_FROM_NAME", "Alex"),
        listing_senders=[s.lower() for s in _list("LISTING_SENDERS")],
        alert_emails=_list("ALERT_EMAILS"),
        dossier_emails=_list("DOSSIER_EMAILS"),
        llm_api_key=env("LLM_API_KEY", ""),
        llm_base_url=env("LLM_BASE_URL", "https://tokenhub.tencentmaas.com/v1"),
        llm_model_chat=env("LLM_MODEL_CHAT", "hy3"),
        llm_model_task=env("LLM_MODEL_TASK", "hy3"),
        llm_reasoning_effort=env("LLM_REASONING_EFFORT", "low"),
        firecrawl_api_key=env("FIRECRAWL_API_KEY", ""),
        timezone=env("TIMEZONE", "Australia/Sydney"),
        reply_debounce_seconds=_int("REPLY_DEBOUNCE_SECONDS", 10),
        reengagement_hour=_int("REENGAGEMENT_HOUR", 9),
        briefing_hour=_int("BRIEFING_HOUR", 8),
        followup_schedule_days=[int(d) for d in schedule] if schedule else [3, 5, 7, 30, 90],
        hot_lead_score=_int("HOT_LEAD_SCORE", 6),
        cron_secret=env("CRON_SECRET", ""),
        support_contact=env("SUPPORT_CONTACT", ""),
        admin_dashboard_key=env("ADMIN_DASHBOARD_KEY", ""),
        cloud_endpoint=env("CLOUD_ENDPOINT", "").rstrip("/"),
        cloud_publishable_key=env("CLOUD_PUBLISHABLE_KEY", ""),
        cloud_oauth_relay=env("CLOUD_OAUTH_RELAY", "").rstrip("/"),
        cloud_admin_email=env("CLOUD_ADMIN_EMAIL", ""),
        cloud_admin_password=env("CLOUD_ADMIN_PASSWORD", ""),
        data_dir=data_dir,
    )


settings = load_settings()
