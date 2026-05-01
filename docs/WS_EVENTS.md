# WS_EVENTS.md — WebSocket 事件规范

> **文档定位**:本文档定义所有 WebSocket 实时事件的契约。
> **依赖**:Schema 引用 `DATA_CONTRACTS.md`,REST 端点引用 `API_SPEC.md`。
> **版本**:v1.0

---

## 0. 协议与基础

### 0.1 技术选型
- **协议**:WebSocket(基于 HTTP/1.1 升级)
- **库**:后端 `python-socketio` + 前端 `socket.io-client`
- **理由**:Socket.IO 提供自动重连、房间机制、心跳保活,比裸 WebSocket 工程化更好

### 0.2 连接信息
- **URL**:`ws://localhost:8000/ws`(开发)→ `wss://...` (生产)
- **认证**:连接时通过 query 参数传 JWT Token:`ws://.../ws?token=<jwt>`
- **认证失败**:服务端立即 disconnect,事件 `auth_error`,payload `{reason}`

### 0.3 心跳
- **客户端**:每 25 秒发 `ping`(Socket.IO 自动)
- **服务端**:超过 60 秒无心跳即断开,前端自动重连

### 0.4 房间(Room)机制
- **commander 房间**:所有指挥员加入,接收 KPI/告警/状态推送
- **admin 房间**:管理员加入,接收审计相关事件
- **session:{session_id}**:回放模式时单独加入(只接收该 session 的回放数据)
- **scenario:{scenario_id}**:仅当前加载场景的客户端接收对应推送

加入房间方式:
- 登录后,前端发 `subscribe` 事件,payload `{rooms: ["commander", "scenario:xxx"]}`
- 服务端验证权限后,加入对应房间

### 0.5 事件命名规范
- 格式:`{域}.{动作}` 全小写,下划线分隔
- 示例:`robot.state_changed`, `task.created`, `alert.raised`

### 0.6 Payload 通用约定
所有 payload 必须包含:
```typescript
{
  event_id: string,        // UUID,事件唯一 ID(用于去重)
  timestamp: string,       // ISO 8601,服务端发送时间
  ...event_specific_data
}
```

---

## 1. 事件方向说明

| 方向 | 说明 |
|---|---|
| **S → C** | 服务端 → 客户端(广播 / 单播)|
| **C → S** | 客户端 → 服务端(主要是订阅、确认)|

---

## 2. 连接生命周期事件

### connect
- **方向**:C → S(自动)
- **触发**:WebSocket 握手成功
- **服务端响应**:发 `welcome` 事件

### welcome (S → C)
- **触发**:握手认证通过后立即发送
- **payload**:
```json
{
  "event_id": "uuid-xxx",
  "timestamp": "2026-04-25T14:32:18Z",
  "session_id": "ws-session-uuid",
  "user": { "id": "...", "username": "...", "roles": [...] },
  "server_time": "2026-04-25T14:32:18Z"
}
```

### subscribe (C → S)
- **触发**:客户端主动订阅房间
- **payload**:
```json
{ "rooms": ["commander", "scenario:uuid-xxx"] }
```
- **服务端响应**:`subscribed` 事件
- **失败**:`subscribe_error` 事件(payload `{room, reason}`)

### subscribed (S → C)
```json
{
  "event_id": "...",
  "timestamp": "...",
  "rooms": ["commander", "scenario:uuid-xxx"]
}
```

### unsubscribe (C → S)
```json
{ "rooms": ["scenario:uuid-old"] }
```

### auth_error (S → C)
- **触发**:Token 失效或被加入黑名单
- **payload**:`{ reason: "token_expired" | "token_revoked" | "invalid" }`
- **客户端处理**:跳转登录页

### disconnect
- **方向**:双向
- **触发**:网络断开或主动断开

---

## 3. 机器人模块事件

### robot.state_changed (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发时机**:机器人状态机发生 FSM 转移时(IDLE→BIDDING 等)
- **频率**:每个机器人每次状态变化触发一次,**非高频**
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "robot_id": "uuid-xxx",
  "robot_code": "UAV-001",
  "from_state": "IDLE",
  "to_state": "BIDDING",
  "current_task_id": "uuid-task-yyy"
}
```

### robot.position_updated (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发时机**:机器人位置变化(由心跳上报触发)
- **频率**:**高频(每机器人 1Hz)**,客户端需做合并渲染
- **batch 模式**:服务端可合并 25 个机器人为一条事件,Payload 是数组
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "updates": [
    {
      "robot_id": "uuid-001",
      "robot_code": "UAV-001",
      "position": { "lat": 30.21, "lng": 120.51, "altitude_m": 50, "heading_deg": 45 },
      "battery": 78.5,
      "fsm_state": "EXECUTING"
    },
    { "robot_id": "uuid-002", ... }
  ]
}
```

### robot.fault_occurred (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发时机**:机器人触发 FAULT
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "robot_id": "...",
  "robot_code": "USV-001",
  "fault_type": "low_battery",
  "severity": "critical",
  "message": "电量降至 12%,无法继续执行任务",
  "fault_id": "uuid-fault-zzz"
}
```

### robot.recall_initiated (S → C)
- **方向**:S → C(广播至 `commander` + `admin`)
- **触发时机**:HITL 召回操作完成
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "robot_id": "...",
  "robot_code": "UAV-003",
  "initiated_by_user_id": "...",
  "reason": "...",
  "intervention_id": "..."
}
```

### robot.recall_completed (S → C)
- **触发**:被召回机器人到达基地,FSM 状态回到 IDLE
- **payload**:同上,加 `eta_actual_sec`

---

## 4. 任务模块事件

### task.created (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:任务创建成功
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "task_id": "...",
  "task_code": "T-2024-001",
  "name": "搜救任务:废墟 A 区",
  "type": "search_rescue",
  "priority": 1,
  "target_area": { ... },
  "created_by": "uuid-user-xxx"
}
```

### task.status_changed (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:任务状态机转移
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "task_id": "...",
  "task_code": "T-2024-001",
  "from_status": "PENDING",
  "to_status": "ASSIGNED",
  "assigned_robot_ids": ["uuid-r1", "uuid-r2"]   // 可选,仅 ASSIGNED 时有
}
```

### task.progress_updated (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:任务进度更新(机器人上报进度时)
- **频率**:中频(任务进度变化 ≥ 5% 时推送,避免刷屏)
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "task_id": "...",
  "task_code": "T-2024-001",
  "progress": 65.0,
  "status": "EXECUTING"
}
```

### task.cancelled (S → C)
- **触发**:任务被取消
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "task_id": "...",
  "task_code": "T-2024-005",
  "cancelled_by_user_id": "...",
  "reason": "现场情况变化",
  "intervention_id": "..."
}
```

### task.reassigned (S → C)
- **触发**:HITL 改派完成
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "task_id": "...",
  "task_code": "T-2024-001",
  "from_robot_id": "uuid-r1",
  "from_robot_code": "UAV-001",
  "to_robot_id": "uuid-r2",
  "to_robot_code": "UAV-002",
  "reassigned_by_user_id": "...",
  "reason": "原机器人电量不足",
  "intervention_id": "..."
}
```

---

## 5. 调度模块事件

### auction.started (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:拍卖开始
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "auction_id": "...",
  "task_id": "...",
  "task_code": "T-2024-001",
  "algorithm": "AUCTION_HUNGARIAN",
  "candidate_robot_count": 8
}
```

### auction.bid_submitted (S → C)
- **方向**:S → C(广播至 `commander`,可被前端忽略以减少噪音)
- **触发**:每个机器人提交出价时
- **频率**:中频(单次拍卖会有 N 条,N=合格机器人数)
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "auction_id": "...",
  "robot_id": "...",
  "robot_code": "UAV-001",
  "bid_value": 1.08,
  "vision_boosted": true
}
```

### auction.completed (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:拍卖关闭、分配方案确定
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "auction_id": "...",
  "task_id": "...",
  "winner_robot_id": "...",
  "winner_robot_code": "UAV-001",
  "winning_bid": 1.08,
  "decision_latency_ms": 1842,
  "total_bidders": 8,
  "vision_boost_applied": true
}
```

### auction.failed (S → C)
- **触发**:无合格机器人,拍卖失败
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "auction_id": "...",
  "task_id": "...",
  "reason": "no_eligible_robot",
  "filtered_out_count": 25
}
```

### dispatch.algorithm_changed (S → C)
- **方向**:S → C(广播至 `commander` + `admin`)
- **触发**:HITL 切换算法
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "from_algorithm": "GREEDY",
  "to_algorithm": "AUCTION_HUNGARIAN",
  "switched_by_user_id": "...",
  "reason": "...",
  "intervention_id": "..."
}
```

---

## 6. 协同通信模块事件(YOLO 视觉感知)

### blackboard.updated (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:黑板条目新建或融合更新
- **频率**:中频
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "key": "survivor:120.51_30.21",
  "value": { "type": "survivor", "position": { "lat": 30.21, "lng": 120.51 } },
  "confidence": 0.94,
  "source_robot_id": "uuid-uav-001",
  "is_fused": true,
  "fusion_source_count": 2
}
```

### perception.detection (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:YOLOv8 检测到目标(无论是否写入黑板)
- **频率**:**高频**,前端需限流(可按 source_robot 节流)
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "source_robot_id": "uuid-uav-003",
  "source_robot_code": "UAV-003",
  "frame_id": "UAV-003-20260425-143218-001",
  "inference_time_ms": 25,
  "detections": [
    {
      "class_name": "fire",
      "confidence": 0.96,
      "bbox": [410, 280, 620, 480],
      "world_position": { "lat": 30.18, "lng": 120.62 }
    }
  ]
}
```

### perception.high_confidence_alert (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:高置信度幸存者(conf ≥ 0.8)被检测到,自动派任务前
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "class_name": "survivor",
  "confidence": 0.92,
  "position": { "lat": 30.21, "lng": 120.51 },
  "source_robot_code": "UAV-001",
  "auto_task_triggered": true,
  "task_id": "uuid-new-task"
}
```

---

## 7. 态势感知模块事件

### kpi.snapshot (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:KPI 聚合服务每秒推送一次
- **频率**:1Hz(节流)
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "online_robots": 24,
  "total_robots": 25,
  "completion_rate": 87.3,
  "avg_response_sec": 42.5,
  "battery_distribution": { "high": 18, "mid": 5, "low": 2 },
  "active_alerts": 7,
  "active_tasks": 13
}
```

### alert.raised (S → C)
- **方向**:S → C(广播至 `commander` + `admin`)
- **触发**:新告警生成
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "alert_id": "...",
  "alert_code": "ALERT-2024-018",
  "severity": "critical",
  "type": "fire_detected",
  "source": "UAV-003",
  "message": "森林 B 区检测到火点(YOLO 置信度 0.96)",
  "related_task_id": null,
  "related_robot_id": "uuid-uav-003",
  "payload": { ... }
}
```

### alert.acknowledged (S → C)
- **触发**:告警被确认
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "alert_id": "...",
  "alert_code": "ALERT-2024-018",
  "acknowledged_by_user_id": "...",
  "acknowledged_at": "..."
}
```

### alert.ignored (S → C)
- **触发**:告警被忽略
- **payload**:同上,加 `reason`

---

## 8. HITL 干预审计事件

### intervention.recorded (S → C)
- **方向**:S → C(广播至 `admin`)
- **触发**:任何 HITL 操作完成后,服务端额外发送一条审计事件
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "intervention_id": "...",
  "user_id": "...",
  "intervention_type": "reassign",
  "target_task_id": "...",
  "target_robot_id": "...",
  "reason": "..."
}
```

> **说明**:`intervention.recorded` 与 `task.reassigned` / `robot.recall_initiated` 等事件**会同时触发**。
> 区别:前者只发给 admin 房间(用于审计页),后者发给 commander(用于业务面板)。

---

## 9. 复盘模块事件

### replay.snapshot (S → C)
- **方向**:S → C(单播给 `session:{id}` 房间内客户端)
- **触发**:回放模式下,按时间轴推送快照
- **频率**:由前端控制(暂停时不推,倍速时调整)
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "session_id": "...",
  "snapshot_time": "2026-04-25T14:18:00Z",
  "robots": [...],
  "tasks": [...],
  "blackboard": [...],
  "alerts": [...]
}
```

### experiment.progress (S → C)
- **方向**:S → C(广播至 `commander`)
- **触发**:实验运行中,每完成一次 run 推送一次
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "batch_id": "...",
  "completed_runs": 24,
  "total_runs": 60,
  "current_algorithm": "GREEDY",
  "estimated_remaining_sec": 320
}
```

### experiment.completed (S → C)
- **触发**:实验全部完成
- **payload**:
```json
{
  "event_id": "...",
  "timestamp": "...",
  "batch_id": "...",
  "total_runs": 60,
  "duration_sec": 940,
  "stats": {
    "AUCTION_HUNGARIAN": { "completion_rate_mean": 87.3, "completion_rate_std": 2.1 },
    "GREEDY": { ... },
    "RANDOM": { ... }
  }
}
```

---

## 10. 客户端事件处理建议

### 10.1 限流与去重

| 事件 | 建议处理 |
|---|---|
| `robot.position_updated` | 1Hz 节流,仅渲染最新位置 |
| `perception.detection` | 按 `source_robot` 分组节流(每秒最多 2 帧)|
| `auction.bid_submitted` | 默认折叠,仅在拍卖详情页展开时显示 |
| `kpi.snapshot` | 直接覆盖 UI,无需累积 |

### 10.2 用 `event_id` 去重
某些事件可能因网络抖动重复推送,前端应用 `event_id` 维护一个 LRU 缓存(容量 1000),已处理过的事件直接跳过。

### 10.3 重连后状态同步
重连后,客户端应:
1. 重新订阅之前的房间
2. 调用对应 REST 接口拉取最新快照(KPI / 当前任务列表 / 当前告警)
3. 之后再开始处理增量 WS 事件

---

## 11. 事件分组优先级(实现顺序)

| 优先级 | 事件 | 备注 |
|---|---|---|
| **P0** | connect / welcome / subscribe | 链路基础 |
| **P0** | robot.position_updated | 地图核心 |
| **P0** | robot.state_changed | 状态变化 |
| **P0** | task.created / task.status_changed | 任务面板核心 |
| **P0** | auction.completed | 拍卖结果 |
| **P0** | alert.raised | 告警弹窗 |
| **P1** | robot.fault_occurred | 故障处理 |
| **P1** | task.reassigned / dispatch.algorithm_changed | HITL |
| **P1** | kpi.snapshot | KPI 实时 |
| **P1** | perception.detection / perception.high_confidence_alert | YOLO 流 |
| **P2** | blackboard.updated | 黑板可视化页 |
| **P2** | replay.snapshot | 回放专用 |
| **P2** | experiment.progress / experiment.completed | 实验专用 |
| **P2** | intervention.recorded | 审计 |

---

## 12. 测试用例提示

### 12.1 关键链路测试

1. **连接 → 订阅 commander → 接收 kpi.snapshot** (基础链路)
2. **创建任务 → 接收 `task.created` → 接收 `auction.started` → 接收 `auction.completed` → 接收 `task.status_changed`** (任务全流程)
3. **改派 API 调用 → 接收 `task.reassigned` + `intervention.recorded`** (HITL 双事件)
4. **YOLO 推理 → 接收 `perception.detection` → 接收 `blackboard.updated`** (CV 流)
5. **重连场景:断网 5s → 自动重连 → 重新订阅 → 历史事件不重复处理**

### 12.2 性能基准

- 25 机器人 × 1Hz = 25 events/s,batch 后 = 1 event/s ✓
- 拍卖期间瞬时事件:~ 10 events/s 短时,前端应能流畅渲染
- 压测:模拟 100 events/s 持续 1 分钟,前端帧率不低于 30 FPS

---

**END OF WS_EVENTS.md**
