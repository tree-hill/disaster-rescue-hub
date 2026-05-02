"""全局常量定义。

对应 BUSINESS_RULES.md §7 阈值汇总表 + CONVENTIONS.md §5.4。
变更时必须同步更新文档。

注：本文件仅按需新增本任务用到的常量；其他模块用到的常量在对应任务时
（按 BUILD_ORDER 推进）增量补充，避免一次性堆砌。
"""
from __future__ import annotations

# === 认证 ===
JWT_ACCESS_TTL_HOURS = 24
JWT_REFRESH_TTL_DAYS = 7
LOGIN_FAIL_LOCKOUT_THRESHOLD = 5  # 连续失败 5 次触发锁定
LOGIN_LOCKOUT_DURATION_MIN = 15   # 锁定 15 分钟

# === 故障检测 ===
# BUSINESS_RULES §2.2.2：battery <= 5% 触发 low_battery（critical）
FAULT_BATTERY_THRESHOLD = 5.0
# 心跳超时（秒）；P3.4 实现 comm_lost 时使用
HEARTBEAT_TIMEOUT_SEC = 15

# === Mock 行为 (P3.4) ===
# EXECUTING 状态每 tick 电量下降 0.5%（BUILD_ORDER §P3.4）
EXECUTING_BATTERY_DRAIN_PCT = 0.5
# EXECUTING 状态每 tick 朝目标移动 1 米（BUILD_ORDER §P3.4）
MOVE_STEP_METERS = 1.0
# 1° lat/lng 在赤道附近 ≈ 111320 米；30°N 时 lng 实际 ≈ 96522 米
# Mock 阶段用统一 111320 简化（误差约 15%，毕设演示可接受）；
# P5 调度的距离计算用真实 haversine
METERS_PER_DEGREE = 111320.0
