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
