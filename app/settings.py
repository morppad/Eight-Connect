import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GatewayConnect"
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8080

    # RP callback security
    RP_CALLBACK_SIGNING_SECRET: str = os.getenv("RP_CALLBACK_SIGNING_SECRET")
    RP_CALLBACK_RETRY_MAX: int = 6
    RP_CALLBACK_BASE_TIMEOUT_SEC: int = 2

    # Default provider selection
    DEFAULT_PROVIDER: str = "Brusnika_SBP"

    # Provider: Brusnika
    BRUSNIKA_BASE_URL: str = "https://api.brusnikapay.top"
    BRUSNIKA_WEBHOOK_URL: str = "shad-mighty-bluegill.ngrok-free.app/provider/brusnika/webhook"
    # BRUSNIKA_API_KEY: str = "REPLACE"
    # BRUSNIKA_WEBHOOK_SIGNING_SECRET: str = "REPLACE"

    # --- Forta ---
    FORTA_BASE_URL: str = "https://pt.wallet-expert.com"
    # FORTA_API_TOKEN: str = ""
    FORTA_WEBHOOK_URL: str = "https://shad-mighty-bluegill.ngrok-free.app/provider/forta/webhook"

    # DB
    DB_URL: str = "sqlite+aiosqlite:///./data/mappings.sqlite3"

settings = Settings()
