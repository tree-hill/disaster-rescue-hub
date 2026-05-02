"""25 个 RobotAgent 的生命周期管理器。

对照 BUILD_ORDER §P3.3：
- start_all：在系统启动时调用，为所有 active 机器人创建协程
- stop_all：优雅关闭

设计要点：
- 单例（FastAPI lifespan 持有引用）；非线程安全（asyncio 单线程足够）
- start_all 用一个 session 加载 robots → 每个 RobotAgent 各自跑独立协程
- stop_all 给每个 agent 发 stop()，再 asyncio.gather(..., return_exceptions=True)
  收集所有协程的退出，超时即强制 cancel
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.agents.robot_agent import RobotAgent
from app.core.config import settings
from app.db.session import async_session_maker
from app.repositories.robot import RobotRepository

logger = logging.getLogger(__name__)


class AgentManager:
    """25 个 RobotAgent 的生命周期管理器（单例）。"""

    _instance: "AgentManager | None" = None

    def __init__(self) -> None:
        self._agents: dict[UUID, RobotAgent] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._started: bool = False

    # ---------- 单例 ----------
    @classmethod
    def get_instance(cls) -> "AgentManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        """仅用于测试：清空单例引用。"""
        cls._instance = None

    # ---------- 查询 ----------
    def get(self, robot_id: UUID) -> RobotAgent | None:
        return self._agents.get(robot_id)

    def list_agents(self) -> list[RobotAgent]:
        return list(self._agents.values())

    @property
    def started(self) -> bool:
        return self._started

    # ---------- 生命周期 ----------
    async def start_all(self) -> None:
        """加载所有 is_active=TRUE 的机器人，为每台创建 RobotAgent 协程。

        重复调用是 no-op（防御 lifespan 误触发两次）。
        """
        if self._started:
            logger.warning("agent_manager_already_started")
            return

        async with async_session_maker() as session:
            robots = await RobotRepository(session).find_all(only_active=True)

        for robot in robots:
            agent = RobotAgent(
                robot_id=robot.id,
                code=robot.code,
                type_=robot.type,
                capability=dict(robot.capability),
                tick_hz=settings.mock_agents_tick_hz,
            )
            self._agents[robot.id] = agent
            self._tasks[robot.id] = asyncio.create_task(
                agent.run(), name=f"agent:{robot.code}"
            )

        self._started = True
        logger.info(
            "agent_manager_started",
            extra={"count": len(self._agents), "tick_hz": settings.mock_agents_tick_hz},
        )

    async def stop_all(self, *, timeout_sec: float = 5.0) -> None:
        """先发送优雅停止信号，再等待协程退出；超时强制 cancel。"""
        if not self._started:
            return

        # 1) 优雅停止：每个 agent 设置 stop_event
        for agent in self._agents.values():
            agent.stop()

        # 2) 等待退出
        if self._tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks.values(), return_exceptions=True),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "agent_manager_stop_timeout, cancelling remaining tasks",
                    extra={"timeout_sec": timeout_sec},
                )
                for task in self._tasks.values():
                    if not task.done():
                        task.cancel()
                # 再等一次，让 cancel 生效
                await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        count = len(self._agents)
        self._agents.clear()
        self._tasks.clear()
        self._started = False
        logger.info("agent_manager_stopped", extra={"count": count})


def get_agent_manager() -> AgentManager:
    """便捷访问器（FastAPI lifespan / 路由依赖注入）。"""
    return AgentManager.get_instance()
