# PROJECT_CONTEXT.md — 项目状态摘要

> **文档定位**:每次新开 Claude Code / Cursor / ChatGPT 会话时,**第一条消息粘贴本文档全文**。它是 AI 进入项目上下文最快的方式。
> **使用方式**:复制本文档 → 粘贴到 AI 工具的第一条消息 → 然后说"按 BUILD_ORDER P3.4 继续推进"即可。
> **维护**:每完成一个阶段更新一次 §6"当前进度"。
> **版本**:v1.0(2026-04-25 初稿)

---

## 1. 项目一句话介绍

**项目名**:`disaster-rescue-hub`

**毕业设计题目**:基于 React 的救灾中枢系统的设计与实现

**核心定位**:面向灾害应急响应的**异构多机器人协同指挥中枢系统**,融合 YOLOv8 视觉感知与人在回路混合决策。

**专业方向**:人工智能(计算机视觉方向)。视觉感知是论文核心创新点之一。

---

## 2. 三大创新点(论文 + 代码都围绕这三点)

1. **融合 YOLOv8 视觉感知与市场拍卖调度的端到端救援决策框架** —— 视觉识别结果直接作为调度算法的输入(高置信度幸存者触发 1.5x 加成)
2. **基于 WebSocket 的人在回路(HITL)混合决策闭环** —— 算法推荐 + 人工干预 + 全程审计
3. **基于统一任务抽象的跨灾害场景架构** —— 地震、火灾共享 90% 核心代码

---

## 3. 系统硬数字(代码与论文必须严格遵循)

| 项 | 值 |
|---|---|
| 机器人总数 | **25 台**(10 UAV + 10 UGV + 5 USV)|
| 数据库表数 | **17 张** |
| 调度算法 | **3 种**:AUCTION_HUNGARIAN(主)、GREEDY、RANDOM |
| 主场景 | 地震废墟搜救 |
| 辅场景 | 森林火灾监测 |
| YOLO 模型 | YOLOv8s,4 类(survivor / collapsed_building / smoke / fire)|
| 数据集 | AIDER(~8400 张航拍图)|
| 实验设计 | 每算法 10 次,共 60 次(2 场景 × 3 算法 × 10 次)|
| 状态推送延迟目标 | < 500 ms |
| 拍卖决策延迟目标 | < 2 s |
| YOLO 推理延迟目标 | < 100 ms (GPU) |
| mAP@0.5 目标 | ≥ 0.75(预期 0.785)|

---

## 4. 技术栈(版本严格锁定,不可随意升级)

### 后端
- Python 3.11
- FastAPI 0.110
- SQLAlchemy 2.0(async)
- PostgreSQL 15.5(必须用 JSONB / GIN 索引)
- Alembic 1.13(迁移)
- python-socketio 5.11(WebSocket)
- Pydantic 2.6
- Ultralytics YOLOv8 8.1
- scipy 1.12(匈牙利算法)
- structlog 24.1(日志)

### 前端
- React 18.2 + TypeScript 5.3
- Vite 5.1
- Zustand(状态)
- React-Konva(地图)
- Recharts / ECharts(图表)
- Tailwind CSS 3.4
- Socket.IO Client 4.7

### 部署
- Docker Compose
- Linux(Ubuntu 22.04)/ Windows / macOS 均可开发

---

## 5. 架构思想

- **领域驱动设计(DDD)**:6 大限界上下文
  1. **Robot**(机器人管理)
  2. **Task**(任务管理)
  3. **Dispatch**(智能调度,核心)⭐
  4. **Communication**(协同通信 + 视觉感知,YOLO 在此层)⭐
  5. **Situational**(态势感知)
  6. **Replay**(复盘与分析)

- **事件驱动架构(EDA)**:基于 `asyncio.Queue` 自研轻量事件总线
- **分层**:API → Service → Repository → Model
- **每个机器人**是一个 asyncio 协程(RobotAgent)

---

## 6. 当前进度(每阶段更新一次)

> **更新方式**:复制本节,把 ✅ 标到已完成的任务上。

```
[✅] P0  项目基建            (Week 1)  ← 2026-05-02 完成
[✅] P1  数据层              (Week 1)  ← 2026-05-02 完成
[ ]  P2  认证 + 基础 API     (Week 2)
[ ]  P3  机器人模块          (Week 2-3)
[ ]  P4  任务模块            (Week 3)
[ ]  P5  调度算法 ⭐核心     (Week 3-4)
[ ]  P6  协同通信 + CV ⭐    (Week 4-5)
[ ]  P7  态势感知 + 前端     (Week 5-6)
[ ]  P8  复盘 + 实验 + 论文  (Week 6-7)
```

**最近完成**:P1.5 Seed 数据脚本(3 角色 + 3 用户 + 3 编队 + 25 机器人 + 1 场景)
**当前任务**:P2.1 配置与依赖注入
**下一步**:P2.2 认证 Schemas + Repository

---

## 7. 关键文档地图(放在 docs/ 下)

| 文档 | 用途 | 何时读 |
|---|---|---|
| **DATA_CONTRACTS.md** | 数据库 DDL + JSONB 结构 + Pydantic Schema | 涉及数据持久化时 |
| **API_SPEC.md** | 所有 REST 接口 | 写路由 / 调 API 时 |
| **WS_EVENTS.md** | 所有 WebSocket 事件 | 写实时推送时 |
| **BUSINESS_RULES.md** | 出价公式 / 状态机 / 规则引擎 / HITL 规则 / 错误码 | 写业务逻辑时 ⭐ |
| **ALGORITHM_TESTCASES.md** | 调度算法测试用例 | 写完算法验证时 |
| **BUILD_ORDER.md** | 阶段→任务→验收清单 | 决定下一步做什么 ⭐ |
| **CONVENTIONS.md** | 命名规范 / 目录结构 / 依赖版本 / 编码风格 | 写代码前必读 ⭐ |
| **PROJECT_CONTEXT.md** | (本文档)项目状态摘要 | 新会话第一条粘贴 |

---

## 8. 关键文件路径(开发时高频访问)

```
docs/                            # 8 份契约文档
backend/app/main.py              # FastAPI 入口
backend/app/core/config.py       # 配置加载
backend/app/core/constants.py    # 全局常量(对应 BUSINESS_RULES §7)
backend/app/core/exceptions.py   # BusinessError
backend/app/db/base.py           # SQLAlchemy Base
backend/app/db/session.py        # async session
backend/app/models/              # ORM 模型(8 个文件)
backend/app/schemas/             # Pydantic Schema(8 个文件)
backend/app/repositories/        # 数据访问层
backend/app/services/            # 业务服务层
backend/app/dispatch/            # 调度子包(算法核心)⭐
backend/app/perception/          # 视觉感知子包(YOLO)⭐
backend/app/communication/       # 黑板 + 信息融合
backend/app/api/v1/              # REST 路由
backend/app/ws/                  # WebSocket
backend/migrations/              # Alembic 迁移
backend/tests/algorithms/        # 算法测试(对照 ALGORITHM_TESTCASES.md)
frontend/src/pages/              # 9 个页面
frontend/src/store/              # Zustand stores
frontend/src/api/                # API 客户端
scripts/seed.py                  # 种子数据
scripts/train_yolo.py            # 模型训练
docker-compose.yml
```

---

## 9. 开发节奏建议

### 9.1 单次会话推进节奏
- 一次会话最多推进 1-2 个 BUILD_ORDER 任务
- 每个任务结束:跑测试 + commit + 更新 §6"当前进度"
- 会话结束前:归纳本次完成的内容,留给下次会话参考

### 9.2 卡点处理
- 算法逻辑卡顿 → 查 `BUSINESS_RULES.md` 对应章节
- 数据结构疑问 → 查 `DATA_CONTRACTS.md`
- API 字段冲突 → 查 `API_SPEC.md`,以契约为准
- 都没找到 → 停下来问用户,**不要瞎猜**

### 9.3 必须遵守的工作流
1. 看 BUILD_ORDER 当前任务
2. 读相关契约文档(2-3 份)
3. 写代码
4. 写测试
5. 跑测试
6. 提交 commit(带任务编号,如 `feat(robot): P3.4 implement agent main loop`)
7. 更新本文档 §6

---

## 10. 需要 AI 严格遵守的规则(给 Claude Code 的指令)

> **复制下面整段作为系统提示词的一部分**:

```
你是 disaster-rescue-hub 项目的开发助手。规则:

1. 写任何代码前,先读 docs/ 下相关的契约文档。当前任务对应的文档优先。

2. 严格遵守:
   - DATA_CONTRACTS.md 的数据库结构和 JSONB 字段格式
   - API_SPEC.md 的 REST 路径、方法、字段
   - WS_EVENTS.md 的事件名、payload
   - BUSINESS_RULES.md 的算法、状态机、错误码
   - CONVENTIONS.md 的命名规范、目录结构、依赖版本

3. 不要自行设计:
   - 不要发明新的数据字段
   - 不要发明新的 API 路径
   - 不要修改算法权重(0.4 / 0.2 / 0.3 / 0.1)
   - 不要修改阈值(电量 20%, 视觉加成 1.5x, 置信度 0.5/0.8 等)

4. 算法相关代码完成后,**自动跑** ALGORITHM_TESTCASES.md 中的对应用例验证。

5. 任何时候发现:
   - 文档中的规定不清楚
   - 不同文档间有冲突
   - 缺少必要的设计决策

   **停下来问用户**,不要"猜测合理"地继续编码。

6. commit message 格式遵循 CONVENTIONS.md §9。每个 commit 必须标注 BUILD_ORDER
   任务编号(如 P3.4)。

7. 完成一个任务后,主动询问用户是否进入下一个任务,不要无限推进。
```

---

## 11. 我(用户)的偏好

> 这部分是用户的工作风格,Claude 应当尊重:

- 偏好**批量交付 + 单次确认**:不喜欢每个小步都问,但关键决策点必须问
- 偏好**实事求是**:不要堆砌虚假赞美
- 偏好**直接说人话**:不要绕弯子,缺信息直接说,有反对意见直接讲
- 已经准备好接受**长期工作**:这个项目预计 7 周,不要催进度
- 喜欢**自圆其说的设计**:遇到设计妥协,把它包装成有意的设计选择(只要符合工程合理性)
- **诚实关于不确定性**:不要把猜测说成确定的

---

## 12. 论文与开发的关系

代码不仅是为了"能跑",还要为论文产出**实际证据**:

| 论文章节 | 代码必须产出 |
|---|---|
| §3.1 需求分析 | (静态文档,代码无关)|
| §3.2 概要设计 | 17 张表 + 6 大领域代码结构 |
| §3.3 详细设计 | 类图对应的实际类代码 |
| §4.2 模块实现 | 6 大模块运行截图 |
| §4.3 模型训练 | YOLOv8 训练曲线 + best.pt + 推理可视化 |
| §4.4 系统运行 | 9 个页面的运行截图 |
| §5.2.3 算法性能 | `experiment_runs` 表 60 条 + 5 张对比图 |
| §5.2.3 模型性能 | mAP@0.5 / Precision / Recall / 混淆矩阵 |

**论文核心数据全部来自系统真实运行,严禁编造**。

---

## 13. 下一步行动(开会话时如果不知道做什么)

按 `BUILD_ORDER.md` 找当前任务:
1. 看 §6 "最近完成" → 找下一个任务
2. 读 BUILD_ORDER.md 中该任务的"验收"
3. 读 BUILD_ORDER.md 中提到的相关契约文档章节
4. 开始写代码

如果项目刚启动:**从 P0.1 开始**。

---

## 14. 一些防翻车的备忘

- ⚠️ Pydantic 不要用 v1 语法(`from pydantic import BaseConfig` 是 v1)
- ⚠️ SQLAlchemy 2.0 必须用 async,旧的 `Session()` 直接同步是 1.x 的写法
- ⚠️ FastAPI 路由不要嵌套 `@router.post` 下再调阻塞函数
- ⚠️ JSONB 写入必须经过 Pydantic 校验,不要直接 dump 字典
- ⚠️ 触发器创建后,Alembic autogenerate 不会检测到,要手写迁移
- ⚠️ React 18 严格模式 useEffect 跑两次,WebSocket 连接要用 useRef 守护
- ⚠️ asyncio 协程中调用同步阻塞函数(如 model.predict),必须用 `asyncio.to_thread`
- ⚠️ 时区:数据库 TIMESTAMPTZ 是 UTC,前端展示要转 Asia/Shanghai
- ⚠️ JWT 不要把敏感信息放 payload,只放 user_id 和 roles

---

## 15. 紧急联系信息(如果 AI 卡住)

如果 AI 在某个问题上卡住超过 5 轮对话仍无进展:
1. 让 AI 列出当前的具体困惑(具体哪个字段、哪个状态、哪个公式)
2. 用户回到 8 份契约文档查找答案
3. 如果文档中确实没有,用户做决定后**回填到对应文档**,然后告诉 AI

**绝对禁止**:用户用"差不多就行"敷衍 AI 的疑问。每次妥协都是后期返工的种子。

---

**END OF PROJECT_CONTEXT.md**
