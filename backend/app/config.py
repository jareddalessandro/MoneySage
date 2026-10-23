from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://moneysage:moneysage@localhost:5433/moneysage"
    price_refresh_hour: int = 17
    price_refresh_minute: int = 30
    price_refresh_tz: str = "America/New_York"
    # Turned off by tests so they never hit the network or start background jobs.
    enable_scheduler: bool = True


settings = Settings()
