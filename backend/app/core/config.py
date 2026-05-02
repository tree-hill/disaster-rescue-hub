from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "disaster"
    db_pass: str = "changeme"
    db_name: str = "disaster_rescue"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # Auth
    jwt_secret: str = "change-me-to-random-string-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_hours: int = 24
    jwt_refresh_ttl_days: int = 7

    # App
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"

    # Mock
    # 默认 False：避免 pytest / 自检脚本启动 FastAPI 时自动起 25 个后台协程。
    # 本地开发若想让 Agent 跑起来，在 backend/.env 显式 MOCK_AGENTS_ENABLED=true。
    mock_agents_enabled: bool = False
    mock_agents_tick_hz: float = 1.0


settings = Settings()
