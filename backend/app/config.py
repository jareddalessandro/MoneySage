import os
from typing import Literal

from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    # The database owner. Migrations run as it.
    database_url: str = "postgresql+psycopg://moneysage:moneysage@localhost:5433/moneysage"
    # When a password is set, the app connects as this separate, non-owner role, so Postgres row-level
    # security applies to every query (a second wall behind the app's own household and company checks).
    # The role is created or updated at startup (python -m app.db_role). Leave it unset for an offline install.
    app_db_user: str = "moneysage_app"
    app_db_password: str | None = None
    # "none": no sign-in; everyone is one automatic local user (an offline install on a trusted network).
    # "google": accounts via Google sign-in, with sharing.
    auth_mode: Literal["none", "google"] = "none"
    # Timezone for new households (the container's TZ by default).
    default_timezone: str = os.environ.get("TZ") or "America/Phoenix"
    price_refresh_hour: int = 17
    price_refresh_minute: int = 30
    price_refresh_tz: str = "America/New_York"
    # Turned off by tests so they never hit the network or start background jobs.
    enable_scheduler: bool = True

    @property
    def app_database_url(self) -> str:
        """What the app's queries connect with: the restricted role if configured, else the owner."""
        if not self.app_db_password:
            return self.database_url
        url = make_url(self.database_url).set(username=self.app_db_user, password=self.app_db_password)
        return url.render_as_string(hide_password=False)


settings = Settings()
