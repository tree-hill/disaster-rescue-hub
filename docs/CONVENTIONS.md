# CONVENTIONS.md — 项目约定与规范

> **文档定位**:本文档定义代码层面的所有约定。**所有文件命名、目录结构、编码风格、错误处理、日志格式等问题,以本文档为准**。
> **使用方式**:Claude Code 写代码前必须知晓本文档,可作为系统提示词的一部分。
> **依赖**:数据契约见 `DATA_CONTRACTS.md`,API 契约见 `API_SPEC.md`,业务规则见 `BUSINESS_RULES.md`。
> **版本**:v1.0

---

## 1. 总则(给 AI 的指令)

### 1.1 核心原则
1. **不要发明新的设计**。所有数据结构、API、状态机均已在契约文档中定义,严格执行。
2. **遇到歧义停下来问**。不要"猜测"用户意图。
3. **写测试,不要跳过**。每个新模块必须有单元测试。
4. **遵守命名规范**,代码即文档。
5. **错误处理统一**,全部走 `BusinessError`,绝不 `print` 或裸 `raise Exception`。
6. **不要引入未列出的依赖**。需要新依赖时先问。

### 1.2 严禁的反模式

❌ 在路由函数里写业务逻辑(应放 service)
❌ 在 service 里直接执行 SQL(应走 repository)
❌ 用 `dict` 当数据载体跨层传递(应用 Pydantic Schema)
❌ JSONB 字段写入未结构化的内容(违反 `DATA_CONTRACTS §4`)
❌ 把 SQL 字段名写成 camelCase(违反 §2 规范)
❌ 用 `print` 替代 logger
❌ 捕获 `Exception` 后吞掉(必须重抛或记录)
❌ 写"魔法数字"(应放 §5.4 的常量定义)

---

## 2. 目录结构

### 2.1 顶层结构

```
disaster-rescue-hub/
├── backend/                      # FastAPI 后端
├── frontend/                     # React 前端
├── docs/                         # 项目文档(8 份契约文档)
│   ├── DATA_CONTRACTS.md
│   ├── API_SPEC.md
│   ├── WS_EVENTS.md
│   ├── BUSINESS_RULES.md
│   ├── ALGORITHM_TESTCASES.md
│   ├── BUILD_ORDER.md
│   ├── CONVENTIONS.md            # ← 当前文档
│   ├── PROJECT_CONTEXT.md
│   └── paper_assets/             # 论文图片素材
├── docker/                       # Docker 配置
│   └── postgres/
│       └── init/                 # 初始化 SQL
├── scripts/                      # 运维脚本
│   ├── seed.py                   # 种子数据
│   ├── prepare_aider.py          # 数据集预处理
│   ├── train_yolo.py             # 模型训练
│   └── start_agents.py           # 启动 Mock Agent
├── tests/                        # 跨服务集成测试
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

### 2.2 Backend 结构(关键!)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI 入口
│   │
│   ├── core/                     # 横切关注点(基础设施)
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic Settings
│   │   ├── security.py           # JWT / 密码哈希
│   │   ├── exceptions.py         # BusinessError 等
│   │   ├── logging.py            # structlog 配置
│   │   ├── event_bus.py          # 事件总线
│   │   └── constants.py          # 全局常量
│   │
│   ├── db/                       # 数据库基础
│   │   ├── __init__.py
│   │   ├── base.py               # SQLAlchemy DeclarativeBase
│   │   └── session.py            # async session factory
│   │
│   ├── models/                   # ORM 模型(每文件 1-3 个相关模型)
│   │   ├── __init__.py
│   │   ├── user.py               # User, Role, UserRole
│   │   ├── robot.py              # Robot, RobotGroup, RobotState, RobotFault
│   │   ├── task.py               # Task, TaskAssignment
│   │   ├── dispatch.py           # Auction, Bid
│   │   ├── intervention.py       # HumanIntervention
│   │   ├── blackboard.py         # BlackboardEntry
│   │   ├── alert.py              # Alert
│   │   └── replay.py             # ReplaySession, ExperimentRun, Scenario
│   │
│   ├── schemas/                  # Pydantic Schemas(API 入参/出参)
│   │   ├── __init__.py
│   │   ├── common.py             # Position, TargetArea, etc.
│   │   ├── auth.py
│   │   ├── robot.py
│   │   ├── task.py
│   │   ├── dispatch.py
│   │   ├── intervention.py
│   │   ├── alert.py
│   │   ├── blackboard.py
│   │   └── error.py
│   │
│   ├── repositories/             # 数据访问层(只与 DB 交互)
│   │   ├── __init__.py
│   │   ├── base.py               # BaseRepository(可选)
│   │   ├── user.py
│   │   ├── robot.py
│   │   ├── robot_state.py
│   │   ├── task.py
│   │   ├── auction.py
│   │   ├── intervention.py
│   │   ├── blackboard.py
│   │   ├── alert.py
│   │   ├── replay.py
│   │   └── experiment.py
│   │
│   ├── services/                 # 业务逻辑层(领域服务)
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── robot_service.py
│   │   ├── task_service.py
│   │   ├── task_status_machine.py
│   │   ├── dispatch_service.py
│   │   ├── intervention_service.py
│   │   ├── alert_service.py
│   │   └── replay_service.py
│   │
│   ├── dispatch/                 # 调度领域(独立子包)
│   │   ├── __init__.py
│   │   ├── rule_engine.py        # 规则引擎
│   │   ├── bidding.py            # 出价计算
│   │   └── algorithms/
│   │       ├── __init__.py       # 工厂方法
│   │       ├── base.py           # 抽象基类
│   │       ├── hungarian.py
│   │       ├── greedy.py
│   │       └── random.py
│   │
│   ├── perception/               # 视觉感知领域(独立子包)
│   │   ├── __init__.py
│   │   ├── service.py            # PerceptionService
│   │   ├── yolo_loader.py        # 模型加载
│   │   └── geo_utils.py          # 像素 → 世界坐标
│   │
│   ├── communication/            # 协同通信领域
│   │   ├── __init__.py
│   │   ├── blackboard.py         # Blackboard 单例
│   │   └── fusion.py             # 信息融合
│   │
│   ├── situation/                # 态势感知领域
│   │   ├── __init__.py
│   │   ├── kpi_aggregator.py
│   │   └── alert_engine.py
│   │
│   ├── agents/                   # Mock 机器人 Agent
│   │   ├── __init__.py
│   │   ├── robot_agent.py
│   │   └── manager.py
│   │
│   ├── experiments/              # 实验运行器
│   │   ├── __init__.py
│   │   └── runner.py
│   │
│   ├── ws/                       # WebSocket
│   │   ├── __init__.py
│   │   ├── server.py             # python-socketio 实例
│   │   └── handlers.py           # 事件处理
│   │
│   └── api/                      # REST 路由
│       ├── __init__.py
│       ├── deps.py               # 依赖注入(get_current_user 等)
│       ├── router.py             # 主 router 聚合
│       └── v1/
│           ├── __init__.py
│           ├── auth.py
│           ├── robots.py
│           ├── tasks.py
│           ├── dispatch.py
│           ├── alerts.py
│           ├── blackboard.py
│           ├── replay.py
│           ├── experiments.py
│           └── admin.py
│
├── tests/                        # 测试
│   ├── __init__.py
│   ├── conftest.py               # 共享 fixtures
│   ├── unit/
│   │   ├── test_bidding.py
│   │   ├── test_rule_engine.py
│   │   ├── test_status_machine.py
│   │   └── test_fusion.py
│   ├── integration/
│   │   ├── test_auth_flow.py
│   │   ├── test_task_flow.py
│   │   └── test_dispatch_flow.py
│   ├── algorithms/               # 算法测试用例(对照 ALGORITHM_TESTCASES.md)
│   │   ├── test_hungarian.py
│   │   ├── test_greedy.py
│   │   └── test_e2e.py
│   └── fixtures/
│       └── test_images/          # YOLO 测试图
│
├── migrations/                   # Alembic 迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── pyproject.toml                # 依赖管理
├── alembic.ini
├── pytest.ini
└── Dockerfile
```

### 2.3 Frontend 结构

```
frontend/
├── public/
├── src/
│   ├── main.tsx                  # 入口
│   ├── App.tsx
│   │
│   ├── api/
│   │   ├── client.ts             # axios 单例
│   │   ├── auth.ts               # 认证 API 调用
│   │   ├── robots.ts
│   │   ├── tasks.ts
│   │   ├── dispatch.ts
│   │   ├── alerts.ts
│   │   ├── blackboard.ts
│   │   └── experiments.ts
│   │
│   ├── store/                    # Zustand
│   │   ├── auth.ts
│   │   ├── ws.ts                 # WebSocket 单例 + 状态
│   │   ├── robots.ts
│   │   ├── tasks.ts
│   │   └── alerts.ts
│   │
│   ├── pages/                    # 页面级组件
│   │   ├── Login.tsx
│   │   ├── Cockpit.tsx           # ⭐ 指挥工作台
│   │   ├── RobotManagement.tsx
│   │   ├── TaskManagement.tsx
│   │   ├── Blackboard.tsx
│   │   ├── AlertCenter.tsx
│   │   ├── Replay.tsx
│   │   ├── Experiment.tsx
│   │   └── Admin.tsx
│   │
│   ├── components/               # 通用组件
│   │   ├── common/               # Button / Input / Toast / Dialog ...
│   │   ├── domain/               # 领域组件(StatusBadge / RobotCard ...)
│   │   ├── map/                  # 地图组件(Konva)
│   │   └── charts/               # 图表组件(ECharts/Recharts)
│   │
│   ├── hooks/                    # 自定义 hooks
│   │   ├── useAuth.ts
│   │   ├── useWebSocket.ts
│   │   └── useRobots.ts
│   │
│   ├── types/                    # TypeScript 类型(对照 DATA_CONTRACTS Schemas)
│   │   ├── common.ts
│   │   ├── robot.ts
│   │   ├── task.ts
│   │   └── ...
│   │
│   ├── router/
│   │   └── index.tsx
│   │
│   ├── utils/
│   │   ├── date.ts               # 时间格式化
│   │   ├── geo.ts                # Haversine 等
│   │   └── format.ts
│   │
│   ├── constants/
│   │   └── index.ts              # 与后端 §5.4 同步的常量
│   │
│   └── styles/
│       ├── global.css
│       └── tokens.ts             # 设计令牌(色板等,对照 figma_design_system)
│
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

---

## 3. 依赖版本(锁定)

### 3.1 后端 Python(`pyproject.toml`)

```toml
[project]
name = "disaster-rescue-hub-backend"
version = "1.0.0"
requires-python = ">=3.11,<3.13"

dependencies = [
    # Web 框架
    "fastapi>=0.110,<0.111",
    "uvicorn[standard]>=0.27,<0.28",
    # ORM 与数据库
    "sqlalchemy>=2.0,<2.1",
    "asyncpg>=0.29,<0.30",
    "alembic>=1.13,<1.14",
    # Schema 校验
    "pydantic>=2.6,<2.7",
    "pydantic-settings>=2.2,<2.3",
    # WebSocket
    "python-socketio>=5.11,<5.12",
    # 安全
    "python-jose[cryptography]>=3.3,<3.4",
    "passlib[bcrypt]>=1.7,<1.8",
    # 日志
    "structlog>=24.1,<25.0",
    # 算法
    "numpy>=1.26,<2.0",
    "scipy>=1.12,<1.13",
    # CV
    "ultralytics>=8.1,<8.2",
    "torch>=2.2,<2.3",
    "opencv-python>=4.9,<4.10",
    "pillow>=10.2,<10.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<8.1",
    "pytest-asyncio>=0.23,<0.24",
    "pytest-cov>=4.1,<4.2",
    "httpx>=0.26,<0.27",
    "ruff>=0.3,<0.4",
    "mypy>=1.9,<1.10",
]
```

**绝对禁止**:不要随意升级到 major 版本(如 pydantic 2 → 3),会有破坏性变更。

### 3.2 前端 Node(`package.json`)

```json
{
  "engines": { "node": ">=18.0.0" },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "zustand": "^4.5.0",
    "@tanstack/react-query": "^5.20.0",
    "axios": "^1.6.0",
    "socket.io-client": "^4.7.0",
    "konva": "^9.3.0",
    "react-konva": "^18.2.0",
    "recharts": "^2.12.0",
    "lucide-react": "^0.330.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.1.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

---

## 4. 命名规范

### 4.1 Python 后端

| 元素 | 规范 | 示例 |
|---|---|---|
| 模块文件 | `snake_case.py` | `dispatch_service.py` |
| 包目录 | `snake_case` | `app/perception/` |
| 类名 | `PascalCase` | `class DispatchService` |
| 函数 / 方法 | `snake_case` | `def compute_full_bid()` |
| 私有方法 | 前缀 `_` | `def _validate_input()` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_BATTERY_PCT = 100.0` |
| 异常类 | `XxxError` 后缀 | `class TaskStatusConflictError` |
| Pydantic Schema | `XxxCreate / XxxRead / XxxUpdate` | `class RobotCreate` |
| ORM 模型 | 表名单数化 + PascalCase | 表 `robots` → 类 `Robot` |
| 测试函数 | `test_<被测对象>_<场景>_<期望>` | `test_bidding_low_battery_returns_zero` |

### 4.2 数据库

| 元素 | 规范 | 示例 |
|---|---|---|
| 表名 | `snake_case` 复数 | `robots`, `human_interventions` |
| 字段名 | `snake_case` | `created_at`, `target_area` |
| 主键 | `id` | 全表统一 |
| 外键 | `<被引用表单数>_id` | `robot_id`, `task_id` |
| 索引 | `idx_<表>_<字段>` | `idx_robots_type` |
| 唯一索引 | `uniq_<表>_<字段>` | `uniq_users_username` |

### 4.3 TypeScript 前端

| 元素 | 规范 | 示例 |
|---|---|---|
| 文件 | 组件用 `PascalCase.tsx`,工具用 `camelCase.ts` | `RobotCard.tsx`, `formatDate.ts` |
| 组件 | `PascalCase` | `function CockpitPage()` |
| Hook | 前缀 `use` + `camelCase` | `useWebSocket()` |
| 类型 / 接口 | `PascalCase` | `interface RobotRead` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_RECONNECT = 5` |
| 状态变量 | `camelCase` | `const [count, setCount] = useState(0)` |

### 4.4 API 路径

- 资源用复数:`/robots`, `/tasks`(非 `/robot`)
- 子资源用嵌套:`/robots/{id}/states`
- 动作用 POST 子路径:`/tasks/{id}/cancel`, `/dispatch/reassign`
- 不要用动词在主路径:❌ `/getRobot`, ✅ `GET /robots/{id}`
- query 参数用 `snake_case`:`/robots?include_inactive=true`

### 4.5 WebSocket 事件名

- 格式 `<域>.<动作>`
- 全小写 + 下划线
- 例:`robot.position_updated`, `task.status_changed`, `auction.completed`

### 4.6 错误码

格式:`{HTTP状态}_{领域}_{子类型}_{序号}`,见 `BUSINESS_RULES.md §6`。

---

## 5. 编码约定

### 5.1 Python 代码风格

**强制**:用 `ruff` 自动格式化与检查。配置:

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "B", "C4", "ISC", "PIE", "RET", "SIM"]
ignore = ["E501"]   # 行长由 formatter 处理

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

**类型注解**:
- 公开函数必须有完整类型注解(参数 + 返回值)
- 使用 `from __future__ import annotations` 启用 PEP 604 union 语法
- `Optional[X]` 改写为 `X | None`

**示例**:

```python
from __future__ import annotations

from uuid import UUID
from datetime import datetime

from app.core.exceptions import BusinessError
from app.schemas.task import TaskRead


async def cancel_task(
    task_id: UUID,
    user_id: UUID,
    reason: str,
) -> TaskRead:
    """
    取消指定任务。

    Args:
        task_id: 任务 ID
        user_id: 操作者 ID
        reason: 取消原因(必须 ≥ 5 字符)

    Returns:
        更新后的任务数据。

    Raises:
        BusinessError: 任务不存在(404)或状态不允许取消(409)。
    """
    if len(reason.strip()) < 5:
        raise BusinessError(
            code="422_INTERVENTION_REASON_INVALID_001",
            message="取消原因至少 5 个字符",
            http_status=422,
        )
    # ...
```

### 5.2 TypeScript 代码风格

**强制**:用 `prettier` + `eslint`。

```json
// .prettierrc
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
```

**类型规则**:
- 不使用 `any`,用 `unknown` 替代
- 接口优先于类型别名(对象类型)
- 启用 `strict: true`

**示例**:

```typescript
import { useEffect, useState } from 'react';
import { fetchRobots } from '@/api/robots';
import type { RobotRead } from '@/types/robot';

interface RobotListProps {
  groupId?: string;
  onSelect?: (robot: RobotRead) => void;
}

export function RobotList({ groupId, onSelect }: RobotListProps) {
  const [robots, setRobots] = useState<RobotRead[]>([]);

  useEffect(() => {
    fetchRobots({ group_id: groupId }).then(setRobots);
  }, [groupId]);

  return (
    <ul>
      {robots.map((robot) => (
        <li key={robot.id} onClick={() => onSelect?.(robot)}>
          {robot.code} - {robot.name}
        </li>
      ))}
    </ul>
  );
}
```

### 5.3 注释规范

- 公共 API / 复杂业务逻辑必须有 docstring
- 用中文写 docstring(论文项目,内部文档无需英文)
- TODO / FIXME 必须带 issue 号或负责人:`# TODO(zhangsan): 优化此处性能`

### 5.4 常量管理

**严禁魔法数字**。所有数值常量必须在以下位置定义:

```python
# backend/app/core/constants.py
"""
全局常量定义。
对应 BUSINESS_RULES.md §7 阈值汇总表。
变更时必须同步更新 BUSINESS_RULES.md。
"""

# === 拍卖出价权重 ===
W1_DISTANCE = 0.40
W2_BATTERY = 0.20
W3_CAPABILITY = 0.30
W4_LOAD = 0.10

# === 视觉加成 ===
VISION_BOOST_FACTOR = 1.5
VISION_BOOST_DISTANCE_THRESHOLD_M = 200
VISION_BOOST_CONFIDENCE_THRESHOLD = 0.8

# === 距离 ===
MAX_BIDDING_DISTANCE_KM = 10.0

# === 规则引擎硬约束 ===
MIN_BATTERY_PCT_DEFAULT = 20.0
MAX_LOAD_PER_ROBOT = 3

# === 故障检测 ===
FAULT_BATTERY_THRESHOLD = 5.0
HEARTBEAT_TIMEOUT_SEC = 15

# === 黑板 TTL ===
BLACKBOARD_VISION_TTL_SEC = 300
BLACKBOARD_ALERT_TTL_SEC = 600
BLACKBOARD_STATE_TTL_SEC = 30

# === YOLO 阈值 ===
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_NMS_IOU = 0.45
YOLO_HIGH_CONFIDENCE_SURVIVOR = 0.8
YOLO_FIRE_ALERT_THRESHOLD = 0.7

# === 性能目标(NFR)===
NFR_STATE_PUSH_LATENCY_MS = 500
NFR_DISPATCH_DECISION_LATENCY_MS = 2000
NFR_YOLO_INFERENCE_LATENCY_MS = 100

# === 认证 ===
JWT_ACCESS_TTL_HOURS = 24
JWT_REFRESH_TTL_DAYS = 7
LOGIN_FAIL_LOCKOUT_THRESHOLD = 5
LOGIN_LOCKOUT_DURATION_MIN = 15
```

前端镜像:

```typescript
// frontend/src/constants/index.ts
export const W1_DISTANCE = 0.4;
export const W2_BATTERY = 0.2;
// ... 同步即可
```

---

## 6. 错误处理

### 6.1 后端 BusinessError

```python
# app/core/exceptions.py
class BusinessError(Exception):
    """所有业务错误的基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: list[dict] | None = None,
    ):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or []
        super().__init__(message)
```

**全局 handler**:

```python
# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import BusinessError

app = FastAPI()

@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request.state.request_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
```

### 6.2 抛错位置

- **路由层**:不抛业务错(由 service 抛)
- **service 层**:抛 `BusinessError`(对应 `BUSINESS_RULES §6` 错误码)
- **repository 层**:不抛业务错,数据库异常向上传播(由 service 包装)
- **未预期错误**:由全局 handler 转为 `500_INTERNAL_ERROR_001`,**不暴露内部细节**给客户端

### 6.3 前端错误处理

```typescript
// src/api/client.ts
import axios, { AxiosError } from 'axios';
import { useAuthStore } from '@/store/auth';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<ErrorResponse>) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
      return;
    }
    // 业务错误展示给用户
    if (error.response?.data?.message) {
      toast.error(error.response.data.message);
    }
    return Promise.reject(error);
  },
);
```

---

## 7. 日志规范

### 7.1 后端 structlog 配置

```python
# app/core/logging.py
import structlog
import logging
import sys

def configure_logging(env: str = "dev"):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if env != "dev"
                else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")

logger = structlog.get_logger()
```

### 7.2 日志使用规范

```python
import structlog
logger = structlog.get_logger()

# 推荐:结构化日志,带上下文
logger.info(
    "auction_completed",
    auction_id=str(auction.id),
    task_id=str(task.id),
    winner_robot_id=str(winner.id),
    decision_latency_ms=latency_ms,
    algorithm="AUCTION_HUNGARIAN",
)

# 错误日志
try:
    await service.do_something()
except Exception as e:
    logger.error(
        "service_failed",
        error_type=type(e).__name__,
        error_msg=str(e),
        exc_info=True,
    )
    raise

# ❌ 不要这样
print(f"auction completed for task {task.id}")          # 用 print
logger.info(f"auction completed for {task.id}")         # 拼字符串
```

### 7.3 日志级别

| 级别 | 用途 |
|---|---|
| `DEBUG` | 详细调试信息(生产环境关闭) |
| `INFO` | 正常业务流程(任务创建、拍卖完成等) |
| `WARNING` | 异常但不影响流程(如重试)|
| `ERROR` | 错误,需要关注(异常未被处理)|
| `CRITICAL` | 严重错误(如数据库不可用)|

### 7.4 日志关键字段(必带)

每条日志推荐包含:
- `event`(英文 snake_case 标识事件,如 `auction_completed`)
- `request_id`(API 请求场景下)
- 业务关键字段(`auction_id` / `task_id` / `robot_id` 等)

---

## 8. 测试约定

### 8.1 测试分层

```
tests/
├── unit/         # 纯函数单元测试,不连数据库
├── integration/  # 整体接口测试,连测试数据库
└── algorithms/   # 算法测试用例(对照 ALGORITHM_TESTCASES.md)
```

### 8.2 命名

```python
# pattern: test_<被测对象>_<场景>_<期望>

def test_compute_distance_score_at_max_distance_returns_zero():
    score = compute_distance_score(pos_a, pos_b_far_away)
    assert score == 0.0

def test_rule_engine_filter_low_battery_robots_out():
    eligible, stats = rule_engine.filter([low_bat_robot], task)
    assert len(eligible) == 0
    assert stats["low_battery"] == 1
```

### 8.3 fixtures 使用

```python
# tests/conftest.py
import pytest

@pytest.fixture
def base_robots():
    """对照 ALGORITHM_TESTCASES §0.2"""
    return [...]

@pytest.fixture
async def db_session():
    """测试数据库 session,函数级别,自动回滚"""
    ...
```

### 8.4 必跑测试

CI(GitHub Actions)中:
```bash
ruff check backend/
mypy backend/app
pytest backend/tests/ -v --cov=app --cov-report=term-missing
```

覆盖率最低要求:`app/dispatch/` 和 `app/services/task_status_machine.py` ≥ 90%。

---

## 9. Git 提交约定

### 9.1 提交信息格式

```
<type>(<scope>): <subject>

<body 可选>

<footer 可选>
```

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | bug 修复 |
| `refactor` | 重构(不改功能)|
| `test` | 新增/修改测试 |
| `docs` | 文档变更 |
| `chore` | 构建/工具变更 |
| `perf` | 性能优化 |

**示例**:
```
feat(dispatch): implement Hungarian auction algorithm

- 实现匈牙利算法求解器,基于 scipy.optimize.linear_sum_assignment
- 支持视觉加成 1.5x(对应 BUSINESS_RULES §1.3)
- 添加 TC-1, TC-2, TC-5 测试用例

Closes #12
```

### 9.2 分支策略

- `main`:主分支(稳定)
- `dev`:开发分支
- `feature/<name>`:功能分支(如 `feature/hungarian-auction`)
- `fix/<name>`:修复分支

毕设场景独立开发,可以简化为只用 `main`,但建议每完成一个 BUILD_ORDER 任务就 commit。

---

## 10. 环境变量

### 10.1 .env.example

```bash
# === Database ===
DB_HOST=localhost
DB_PORT=5432
DB_USER=disaster
DB_PASS=changeme
DB_NAME=disaster_rescue

# === Auth ===
JWT_SECRET=change-me-to-random-string-at-least-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_HOURS=24
JWT_REFRESH_TTL_DAYS=7

# === Server ===
APP_ENV=dev               # dev | prod
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO

# === Frontend ===
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000/ws

# === YOLO ===
YOLO_MODEL_PATH=./models/yolov8s_aider_best.pt
YOLO_DEVICE=cuda          # cuda | cpu

# === Mock ===
MOCK_AGENTS_ENABLED=true
MOCK_AGENTS_TICK_HZ=1
```

### 10.2 配置加载

```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    db_host: str
    db_port: int = 5432
    db_user: str
    db_pass: str
    db_name: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_hours: int = 24
    jwt_refresh_ttl_days: int = 7

    # App
    app_env: str = "dev"
    # ...

settings = Settings()
```

---

## 11. 安全约定

| 项 | 规则 |
|---|---|
| 密码 | bcrypt(work factor 12),不可写明文 |
| Token | JWT,不放敏感数据(只放 user_id, roles)|
| 日志 | 严禁记录密码、Token、个人信息 |
| 错误信息 | 不向客户端暴露内部异常细节(stack trace 等)|
| SQL | 必须用 ORM 或参数化查询,严禁拼字符串 |
| 跨域 | 仅允许已知前端域(配置在 CORSMiddleware) |
| 文件上传 | 限制类型与大小(若启用)|

---

## 12. 性能约定

### 12.1 数据库
- 列表查询必须分页,默认 20,最大 100
- N+1 用 `selectinload` / `joinedload` 解决
- 高频写入表(`robot_states`, `blackboard_entries`)用 BIGSERIAL 主键

### 12.2 异步
- I/O 操作必须 async(数据库、HTTP、WS)
- CPU 密集(YOLO 推理、匈牙利算法在大规模)用 `asyncio.to_thread()` 不阻塞事件循环

### 12.3 前端
- 列表 > 100 项用虚拟滚动
- 高频 WS 事件(位置更新)节流,同步到 store 不要每帧 setState
- 地图渲染用 React-Konva 的 Layer 缓存,只在数据变化时重绘

---

## 13. 前后端类型对齐

### 13.1 同步策略

后端 Pydantic Schema → 前端 TypeScript Interface,**一一对应**。

| 后端 (Pydantic) | 前端 (TypeScript) |
|---|---|
| `class RobotRead(BaseModel)` | `interface RobotRead` |
| `Optional[X]` | `X \| null` |
| `datetime` | `string`(ISO 8601)|
| `UUID` | `string` |
| `Decimal` | `number` |
| `Literal["a", "b"]` | `'a' \| 'b'` |

**示例**:

```python
# backend
class RobotRead(BaseModel):
    id: UUID
    code: str
    type: Literal["uav", "ugv", "usv"]
    battery: float
    is_active: bool
    created_at: datetime
```

```typescript
// frontend/src/types/robot.ts
export interface RobotRead {
  id: string;
  code: string;
  type: 'uav' | 'ugv' | 'usv';
  battery: number;
  is_active: boolean;
  created_at: string;
}
```

### 13.2 (可选)自动生成
后期可以用 `datamodel-code-generator` 从 OpenAPI 自动生成 TS 类型,本期手写。

---

## 14. 文档维护

### 14.1 何时更新文档

| 触发条件 | 必须更新的文档 |
|---|---|
| 新增数据库字段 | `DATA_CONTRACTS.md` §1, §4(若 JSONB)|
| 新增 API 接口 | `API_SPEC.md` |
| 新增 WS 事件 | `WS_EVENTS.md` |
| 调整业务规则/阈值 | `BUSINESS_RULES.md` + `app/core/constants.py` |
| 新增依赖 | `CONVENTIONS.md` §3 + `pyproject.toml` |

### 14.2 文档变更记录

每份文档顶部的"版本"字段必须更新。重大变更在 commit message 注明:

```
docs(business-rules): adjust vision boost threshold from 0.7 to 0.8

Updated BUSINESS_RULES.md §1.3 and app/core/constants.py.
Reason: 0.7 误触发率高,实测 0.8 更稳定。
```

---

## 15. 给 Claude Code 的特别提示

> 把以下段落作为 Claude Code 系统提示词的一部分:

```
你是 disaster-rescue-hub 项目的开发助手。在写任何代码前:

1. 必须先读 docs/ 下的 8 份契约文档(尤其是当前任务相关的)。
2. 严格按 CONVENTIONS.md 的目录结构、命名规范、依赖版本编码。
3. 涉及业务逻辑必须查 BUSINESS_RULES.md,不要自己设计。
4. 涉及数据结构必须用 DATA_CONTRACTS.md 中的 schema,不要重新定义。
5. 涉及 API 必须按 API_SPEC.md 定义的路径、方法、字段实现。
6. 涉及 WS 必须按 WS_EVENTS.md 定义的事件名、payload 格式发送。
7. 算法相关代码完成后,跑 ALGORITHM_TESTCASES.md 中的对应用例验证。
8. 文档之间冲突时,以后期/具体的为准,并在 commit 中标注变更。
9. 遇到歧义或缺失信息,停下来问我,不要猜测。
10. 每完成一个 BUILD_ORDER 中的任务,在 commit message 中标记任务编号(如 P3.4)。
```

---

**END OF CONVENTIONS.md**
