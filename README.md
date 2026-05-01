# disaster-rescue-hub

基于 React 的救灾中枢系统的设计与实现。

本项目是一个面向灾害应急响应场景的异构多机器人协同指挥中枢系统，融合 YOLOv8 视觉感知、市场拍卖调度算法、WebSocket 实时通信和人在回路混合决策。

## 文档

项目开发严格遵循 `docs/` 目录下的契约文档：

- `PROJECT_CONTEXT.md`：项目背景与状态
- `BUILD_ORDER.md`：开发阶段与任务顺序
- `CONVENTIONS.md`：目录结构与代码规范
- `DATA_CONTRACTS.md`：数据库与数据结构
- `API_SPEC.md`：REST API 规范
- `WS_EVENTS.md`：WebSocket 事件规范
- `BUSINESS_RULES.md`：业务规则与算法逻辑
- `ALGORITHM_TESTCASES.md`：调度算法测试用例