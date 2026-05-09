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
    # 概率注入故障（BUSINESS_RULES §2.2.2 第 4 项，演示用）
    # 默认 0.0 关闭；答辩演示时调到 0.001（每 Agent 每 tick 0.1% 概率）
    mock_fault_inject_probability: float = 0.0

    # Dispatch 自动化（P5.7）
    # task.created 事件 → 自动触发 start_auction；PENDING 任务每 N 秒重扫一次。
    # 默认开启；自检 / 不希望任务自动拍卖的场景可通过 .env 关掉，或把 interval 设为 0
    # 来仅停 scanner（auto_trigger 仍会响应 task.created）。
    dispatch_auto_trigger_enabled: bool = True
    dispatch_pending_scan_interval_sec: float = 30.0

    # 黑板 TTL 清理（P6.1）
    # BUILD_ORDER §P6.1：定时任务每分钟清理过期条目。
    # 设为 0 即禁用 scanner（pytest / 自检场景）。
    blackboard_cleanup_interval_sec: float = 60.0

    # Mock 视觉数据流（P6.9）
    # 仅 has_yolo=True 的机器人触发；启用后 RobotAgent 每 N tick 调一次
    # PerceptionService.process_image（mock detection 生成器，不依赖 AIDER）。
    # 默认 False：pytest / 自检不跑。演示时开启 + 调 detection_rate 即可看到全链路。
    mock_perception_enabled: bool = False
    # 每 N tick 触发一次推理（默认每 tick 都跑，与 BUSINESS_RULES §5.1 1Hz 一致；
    # tick_hz=1 时 N=1 即 1Hz）
    mock_perception_tick_interval: int = 1
    # 单次推理产生 detection 的概率（演示/答辩场景调 0.05~0.2 比较直观）
    mock_perception_detection_rate: float = 0.0


settings = Settings()
