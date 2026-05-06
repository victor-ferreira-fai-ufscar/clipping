from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Clipping Scraper API"
    clipping_url: str = "https://www.ccs.ufscar.br/clipping"
    default_limit: int = 50
    request_timeout: float = 20.0
    request_delay_seconds: float = 0.35
    headless: bool = True
    max_article_fetches: int = 200
    max_listing_pages: int | None = None
    names_file: Path = PROJECT_ROOT / "assets" / "nomes.csv"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLIPPING_",
        extra="ignore",
    )


settings = Settings()
