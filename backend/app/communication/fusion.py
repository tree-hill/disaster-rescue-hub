"""黑板信息融合（P6.2）。

对照：
- BUILD_ORDER §P6.2：weighted_average / resolve_conflict / fused_from 审计字段
- DATA_CONTRACTS §4.10：fused_from = [{robot_id, confidence, timestamp, weight}]，
  所有 weight 之和 = 1
- DATA_CONTRACTS §4.9：value 字段（type / position / area_m2 / intensity /
  detected_count + 自由扩展）

设计边界：
- 本模块零 IO、纯函数：FusionInput → (value, confidence, fused_from)；与 P5 dispatch
  纯函数风格一致，便于单测与论文复现
- **type 冲突解决**：按 timestamp DESC，平手时 confidence DESC（resolve_conflict）；
  非获胜 type 的 source 不参与 weighted_average，但**仍写入 fused_from 审计**（论文：
  「冲突来源也要可追溯」），其 weight=0
- **加权平均权重**：用 confidence 本身作为权重（同 type 内归一化）
- **数值字段** position.lat/lng / area_m2 / detected_count 走加权平均；intensity 不是数值
  → 选最高 confidence 来源的值（与论文「类别字段按可信度投票」一致）
- **融合 confidence**：取同 type 内 max（保守：融合后整体不应弱于最强单一来源），与
  vision_boost 触发用的 ≥0.8 阈值兼容（避免被低置信度来源拉低）
- **detected_count 取整**：JSONB 接受 float，但语义是整数；用 round() 取整
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class FusionInput:
    """融合输入单元。每个 source 一条；调用方负责把 BlackboardEntrySnapshot
    与新写入合并成 list[FusionInput]。"""

    robot_id: UUID | None
    confidence: float
    timestamp: datetime
    value: dict[str, Any]


# ---------- 公开 API：3 个纯函数 ----------


def weighted_average(values: list[float], weights: list[float]) -> float:
    """加权平均。len(values) == len(weights) 且 sum(weights) > 0。

    BUSINESS_RULES §7：黑板融合用 confidence 作为权重；本函数不绑定权重含义，由
    调用方传入。
    """
    if len(values) != len(weights):
        raise ValueError("values / weights length mismatch")
    total = math.fsum(weights)
    if total <= 0:
        raise ValueError("weights sum must be > 0")
    return math.fsum(v * w for v, w in zip(values, weights)) / total


def resolve_conflict(inputs: list[FusionInput]) -> str:
    """类型冲突解决：返回获胜的 value['type']。

    规则（BUILD_ORDER §P6.2「类型冲突时按时间最新或置信度最高」）：
    1) timestamp DESC（最新优先）
    2) confidence DESC（同时间）
    """
    if not inputs:
        raise ValueError("inputs empty")
    best = max(inputs, key=lambda i: (i.timestamp, i.confidence))
    winning_type = best.value.get("type")
    if not isinstance(winning_type, str):
        raise ValueError("winning input has no string 'type'")
    return winning_type


def fuse_inputs(
    inputs: list[FusionInput],
) -> tuple[dict[str, Any], float, list[dict[str, Any]]]:
    """主入口：多 source 融合。

    返回 (fused_value, fused_confidence, fused_from)。

    流程：
    1. resolve_conflict 决定 winning_type
    2. 同 type sources 走 weighted_average（position.lat/lng / area_m2 / detected_count）
    3. intensity 取最高 confidence source 的值
    4. winning_type 之外的扩展字段保留：取最高 confidence 同 type source 的字段（避免丢
       自由扩展数据）
    5. fused_confidence = max(同 type confidence)
    6. fused_from 写所有 input（含落败 type，weight=0）
    """
    if not inputs:
        raise ValueError("inputs empty")

    winning_type = resolve_conflict(inputs)
    winners = [i for i in inputs if i.value.get("type") == winning_type]
    losers = [i for i in inputs if i.value.get("type") != winning_type]

    win_weights_sum = math.fsum(i.confidence for i in winners)
    if win_weights_sum <= 0:
        # 兜底：所有 winner 的 confidence 都是 0（INV-5 应已拦截，这里防御）
        win_weights_sum = float(len(winners))
        win_weights = [1.0] * len(winners)
    else:
        win_weights = [i.confidence for i in winners]

    fused_value: dict[str, Any] = {"type": winning_type}

    # --- position（lat/lng 加权平均）---
    pos_pairs = [
        (i.value["position"], i.confidence)
        for i in winners
        if isinstance(i.value.get("position"), dict)
        and isinstance(i.value["position"].get("lat"), (int, float))
        and isinstance(i.value["position"].get("lng"), (int, float))
    ]
    if pos_pairs:
        positions = [p for p, _ in pos_pairs]
        pos_w = [w for _, w in pos_pairs]
        fused_pos: dict[str, float] = {
            "lat": weighted_average([float(p["lat"]) for p in positions], pos_w),
            "lng": weighted_average([float(p["lng"]) for p in positions], pos_w),
        }
        # 保留 altitude_m / heading_deg 中最大 confidence 的（可选字段）
        for opt_field in ("altitude_m", "heading_deg"):
            best_opt = _pick_max_conf(
                [
                    (i.confidence, i.value["position"].get(opt_field))
                    for i in winners
                    if isinstance(i.value.get("position"), dict)
                ]
            )
            if best_opt is not None:
                fused_pos[opt_field] = best_opt
        fused_value["position"] = fused_pos

    # --- 数值字段加权平均 ---
    for num_field, is_int in (("area_m2", False), ("detected_count", True)):
        pairs = [
            (float(i.value[num_field]), i.confidence)
            for i in winners
            if isinstance(i.value.get(num_field), (int, float))
            and not isinstance(i.value.get(num_field), bool)
        ]
        if pairs:
            avg = weighted_average([v for v, _ in pairs], [w for _, w in pairs])
            fused_value[num_field] = int(round(avg)) if is_int else avg

    # --- intensity（类别字段，按 confidence 投票）---
    intensity = _pick_max_conf(
        [(i.confidence, i.value.get("intensity")) for i in winners]
    )
    if intensity is not None:
        fused_value["intensity"] = intensity

    # --- 自由扩展字段：保留最高 confidence winner 的非内置字段 ---
    builtin = {"type", "position", "area_m2", "intensity", "detected_count"}
    for i in sorted(winners, key=lambda x: x.confidence):  # 升序，让高 conf 后写覆盖
        for k, v in i.value.items():
            if k not in builtin:
                fused_value[k] = v

    fused_confidence = max(i.confidence for i in winners)

    # --- fused_from 审计 ---
    fused_from: list[dict[str, Any]] = []
    for i, w in zip(winners, win_weights):
        fused_from.append(_make_source(i, weight=w / win_weights_sum))
    for i in losers:
        fused_from.append(_make_source(i, weight=0.0))

    return fused_value, fused_confidence, fused_from


# ---------- 内部工具 ----------


def _pick_max_conf(pairs: list[tuple[float, Any]]) -> Any:
    """从 [(confidence, value), ...] 选最大 confidence 对应的非 None value。"""
    best: tuple[float, Any] | None = None
    for conf, val in pairs:
        if val is None:
            continue
        if best is None or conf > best[0]:
            best = (conf, val)
    return best[1] if best is not None else None


def _make_source(i: FusionInput, *, weight: float) -> dict[str, Any]:
    return {
        "robot_id": str(i.robot_id) if i.robot_id is not None else None,
        "confidence": float(i.confidence),
        "timestamp": i.timestamp.isoformat(),
        "weight": float(weight),
    }
