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

# === 召回与基地 (P3.6) ===
# 演练区中心，与 scripts/seed.py CENTER_LAT/LNG 对齐；所有 Agent 启动初始位置
# 与 RETURNING 阶段的目标位置都是基地。
BASE_LAT = 30.225
BASE_LNG = 120.525
BASE_ALTITUDE_M = 50.0
# BUSINESS_RULES §2.2.3：RETURNING → IDLE 触发条件「距基地 < 50m」
RETURNING_ARRIVAL_THRESHOLD_M = 50.0

# === HITL 干预 (P3.6) ===
# BUSINESS_RULES §4.3.1：reason 长度 5–500 字符
RECALL_REASON_MIN_LEN = 5
RECALL_REASON_MAX_LEN = 500

# === 任务模块 (P4.3) ===
# BUSINESS_RULES §7：area_km2 > 1 触发网格分解；切分粒度 500m × 500m
TASK_GRID_DECOMPOSE_THRESHOLD_KM2 = 1.0
TASK_GRID_TILE_METERS = 500.0
# T-YYYY-NNN 主码序号宽度（不足补零；溢出时按实际位数输出，不截断）
TASK_CODE_SEQ_WIDTH = 3
# 子任务后缀 -CC 序号宽度（同上）
TASK_CHILD_CODE_SEQ_WIDTH = 2
