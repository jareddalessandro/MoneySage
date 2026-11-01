import os
from typing import Literal

from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    # The database owner. Migrations run as it.
    database_url: str = "postgresql+psycopg://tallyvio:tallyvio@localhost:5433/tallyvio"
    # When a password is set, the app connects as this separate, non-owner role, so Postgres row-level
    # security applies to every query (a second wall behind the app's own household and company checks).
    # The role is created or updated at startup (python -m app.db_role). Leave it unset for an offline install.
    app_db_user: str = "tallyvio_app"
    app_db_password: str | None = None
    # "none": no sign-in; everyone is one automatic local user (an offline install on a trusted network).
    # "google": accounts via Google sign-in, with sharing.
    auth_mode: Literal["none", "google"] = "none"
    # From a Google Cloud "OAuth client ID" (type Web application). Its authorized redirect URI must be
    # {public_url}/api/auth/callback.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # The address people open the app at, with no trailing slash. An https address also makes the session
    # cookie Secure.
    public_url: str = "http://localhost:5180"
    # Comma-separated emails allowed to sign in (case doesn't matter). Empty lets any Google account in.
    allowed_emails: str = ""
    # A session ends after this many days without use.
    session_days: int = 30
    # Shown on the landing page, Privacy Policy and Terms (who runs this site and how to reach them, and
    # whose law the Terms follow, e.g. "Arizona, United States"). Set them before opening sign-ups.
    operator_name: str = ""
    contact_email: str = ""
    governing_law: str = ""
    # Timezone for new households (the container's TZ by default).
    default_timezone: str = os.environ.get("TZ") or "America/Phoenix"
    # Where daily prices come from: "yahoo" (yfinance; no account, personal use) or "tiingo" (TIINGO_API_KEY).
    price_provider: Literal["yahoo", "tiingo"] = "yahoo"
    tiingo_api_key: str | None = None
    price_refresh_hour: int = 17
    price_refresh_minute: int = 30
    price_refresh_tz: str = "America/New_York"
    # Turned off by tests so they never hit the network or start background jobs.
    enable_scheduler: bool = True
    # Per-visitor request limits (app.ratelimit). Tests turn them off.
    rate_limit_enabled: bool = True
    # The interactive API docs at /docs. Production turns them off (API_DOCS=false).
    api_docs: bool = True

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def allowed_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    @property
    def app_database_url(self) -> str:
        """What the app's queries connect with: the restricted role if configured, else the owner."""
        if not self.app_db_password:
            return self.database_url
        url = make_url(self.database_url).set(username=self.app_db_user, password=self.app_db_password)
        return url.render_as_string(hide_password=False)


settings = Settings()
