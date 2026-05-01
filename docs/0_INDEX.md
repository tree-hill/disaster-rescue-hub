# 📚 救灾中枢系统 — Vibe Coding 文档套件总览

> 这是一份**索引**,告诉你 8 份文档怎么用、什么时候用哪份。
> 把所有文档一起放到 `docs/` 目录,即可开始 vibe coding。

---

## 🎯 套件成员(8 份)

```
docs/
├── 0_INDEX.md                    ← 你正在读的这份(可选)
│
├── 📋 契约层(最重要,定义"什么是对的")
├── DATA_CONTRACTS.md             # 数据库 + JSONB 结构 + Pydantic Schema
├── API_SPEC.md                   # 所有 REST 接口
├── WS_EVENTS.md                  # 所有 WebSocket 事件
│
├── 📐 业务规则层(定义"怎么算才对")
├── BUSINESS_RULES.md             # 出价公式 / 状态机 / 规则引擎 / HITL / 错误码
├── ALGORITHM_TESTCASES.md        # 调度算法 10 组测试用例 + 3 组 E2E
│
└── 🚀 开发执行层(定义"怎么干")
    ├── BUILD_ORDER.md            # 9 阶段 70 任务的开发顺序
    ├── CONVENTIONS.md            # 命名 / 目录 / 依赖 / 错误处理 / 日志
    └── PROJECT_CONTEXT.md        # 新会话第一条粘贴的项目状态
```

---

## ⚡ 快速开始(3 步)

### Step 1:把 8 份文档放进项目
```bash
mkdir -p disaster-rescue-hub/docs
cp /path/to/*.md disaster-rescue-hub/docs/
cd disaster-rescue-hub
git init && git add docs/ && git commit -m "docs: add contract documents"
```

### Step 2:开 Claude Code 会话,粘贴 PROJECT_CONTEXT
打开 Claude Code(或 Cursor / ChatGPT),第一条消息粘贴:
```
[PROJECT_CONTEXT.md 全文]
```

### Step 3:开始第一个任务
第二条消息说:
> 按 BUILD_ORDER.md P0.1,创建项目骨架。开始前先确认你已经读了
> CONVENTIONS.md 的目录结构章节。

---

## 🔍 决策树:遇到问题该查哪份?

```
问题:我要写...
│
├─ 一个新的数据库字段?      → DATA_CONTRACTS.md §1
├─ 一个 JSONB 内部字段?      → DATA_CONTRACTS.md §4
├─ 一个 API 路由?            → API_SPEC.md(对应模块章节)
├─ 一个 WebSocket 事件?      → WS_EVENTS.md
├─ 一个状态机转移?           → BUSINESS_RULES.md §2
├─ 一个出价公式实现?         → BUSINESS_RULES.md §1
├─ 一个规则引擎判断?         → BUSINESS_RULES.md §3
├─ 一个 HITL 操作?           → BUSINESS_RULES.md §4
├─ 一个错误码?               → BUSINESS_RULES.md §6
├─ 一个文件目录?             → CONVENTIONS.md §2
├─ 一个变量命名?             → CONVENTIONS.md §4
├─ 一个常量数值?             → CONVENTIONS.md §5.4
├─ 一个测试用例?             → ALGORITHM_TESTCASES.md
├─ 不知道下一步做什么?       → BUILD_ORDER.md §6
└─ 项目大背景?               → PROJECT_CONTEXT.md
```

---

## 🎬 典型工作流

### 场景 A:新功能开发
```
1. 看 BUILD_ORDER.md → 确认当前任务编号(如 P3.4)
2. 看 CONVENTIONS.md §2 → 确认代码放哪个目录
3. 看 BUSINESS_RULES.md → 确认相关业务规则
4. 看 DATA_CONTRACTS.md → 确认数据结构
5. 看 API_SPEC.md / WS_EVENTS.md → 确认接口契约
6. 写代码 + 写测试
7. 跑测试,全绿才提交
8. commit + 在 PROJECT_CONTEXT.md §6 标记完成
```

### 场景 B:调试 / 修 bug
```
1. 看 BUSINESS_RULES.md §6 → 确认错误码含义
2. 看 ALGORITHM_TESTCASES.md → 是否有对应的边界用例没覆盖
3. 修复 + 补测试
4. commit
```

### 场景 C:论文撰写阶段
```
1. 系统跑实验:对照 BUILD_ORDER P8.3
2. 实验数据:从 experiment_runs 表导出
3. 论文素材:对照已交付的「论文写作输入文档」+ 截图
4. 答辩 PPT:用 docs/paper_assets/ 中的图
```

---

## 🚨 常见误区

### ❌ "我先随便写一下,后面再对齐文档"
- 这是返工最大的源头
- 写之前 3 分钟读文档,胜过事后 3 小时改

### ❌ "这个字段 / 数值文档没写,我估个值"
- **停下来。回头查 BUSINESS_RULES.md §7 阈值汇总表**
- 真没有,问用户或在文档里补,**不要在代码里硬编码**

### ❌ "把 DATA_CONTRACTS 复制一份当 Schema 用"
- 错。DATA_CONTRACTS 的 SQL 是数据库,Pydantic Schema 是 API 契约,二者**结构相似但目的不同**
- 一律用 §5 的 Pydantic Schema 草案

### ❌ "API 设计跟 API_SPEC 不太一样,我按自己的来"
- API_SPEC 是规约,客户端按它对接
- 偏离规约 = 集成时翻车
- 必须改时,改 API_SPEC 然后通知前端

---

## 📊 文档健康度自检

每周检查一次,看是否健康:

- [ ] PROJECT_CONTEXT.md §6 进度是否最新?
- [ ] 新增的字段是否补到了 DATA_CONTRACTS.md?
- [ ] 新增的 API 是否补到了 API_SPEC.md?
- [ ] 新增的常量是否在 CONVENTIONS.md §5.4 列出?
- [ ] BUSINESS_RULES.md §7 阈值表是否与 `app/core/constants.py` 一致?

不一致就是 bug 的种子。

---

## 🎓 论文与代码的对齐

| 论文章节 | 主要文档 | 代码产出 |
|---|---|---|
| §3.2 概要设计 | DATA_CONTRACTS, API_SPEC | 17 表 + 9 模块代码结构 |
| §3.3 详细设计 | BUSINESS_RULES | 类实现 + 状态机 |
| §4.2 模块实现 | BUILD_ORDER P3-P7 | 各模块运行截图 |
| §4.3 模型训练 | BUILD_ORDER P6.4-P6.5 | YOLO 训练曲线 + 推理图 |
| §5.2 测试 | ALGORITHM_TESTCASES | 60 次实验数据 + 5 张对比图 |

---

## 💡 给 AI 的提示词模板(可直接复制)

把以下内容放在 Claude Code / Cursor 的 system prompt 或第一条消息开头:

```
你是 disaster-rescue-hub 项目的开发助手。

【上下文】
项目是一个本科毕业设计:基于 React 的救灾中枢系统,融合 YOLOv8 与
市场拍卖调度。技术栈:FastAPI + PostgreSQL + React + YOLOv8。

【契约文档】
所有设计已固化在 docs/ 下的 8 份文档中:
- DATA_CONTRACTS.md(数据库 + Pydantic Schema)
- API_SPEC.md(REST 接口)
- WS_EVENTS.md(WebSocket 事件)
- BUSINESS_RULES.md(算法 + 状态机 + 错误码)
- ALGORITHM_TESTCASES.md(测试用例)
- BUILD_ORDER.md(开发顺序)
- CONVENTIONS.md(代码规范)
- PROJECT_CONTEXT.md(项目摘要)

【规则】
1. 写代码前先读相关契约文档
2. 严格遵守 CONVENTIONS.md 的目录结构和命名
3. 不要自行设计未在契约中的数据结构、API、阈值
4. 算法代码完成后必须跑 ALGORITHM_TESTCASES 验证
5. 文档间冲突时,以更具体的为准
6. 缺信息或有歧义时,停下来问,不要猜测
7. commit message 标注 BUILD_ORDER 任务编号(如 P3.4)
8. 完成一个任务主动停下来确认,不要自动推进多个任务

我会按 BUILD_ORDER 的顺序给你下任务。开始之前,告诉我你已读了
PROJECT_CONTEXT.md 和当前任务相关的文档,并简要确认你的理解。
```

---

## 🏁 结语

这套文档把"开发"从**反复对齐设计**变成**纯粹执行**。
你的任务是**严守纪律**:**让每一行代码都是契约的实现,而不是想到哪写到哪**。

祝顺利。
