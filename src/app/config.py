from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "dev"  # dev | test | prod
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///./app.db"
    # Эндпоинты /debug/* для генерации ошибок и задержек. Включать только в тесте.
    enable_debug_endpoints: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
