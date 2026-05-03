"""python-socketio AsyncServer 单例。

对照：
- WS_EVENTS §0.1（python-socketio + socket.io-client）
- WS_EVENTS §0.2（URL：ws://localhost:8000/ws）
- WS_EVENTS §0.3（心跳 25s ping / 60s 超时）

设计：
- AsyncServer 单例（模块级），由 main.py 用 socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
  挂到根路径下；socketio_path 取 "ws" 让真实 URL 为 ws://host:port/ws/?EIO=4&...，
  与 WS_EVENTS 文档书写的 ws://.../ws 对齐
- handlers/broadcaster 各自 import 这里的 sio；handlers 注册由 main.py 显式调用
  register_handlers(sio) 完成（避免 import side effect）
- CORS 与 FastAPI 同源（仅 http://localhost:5173 开发前端）
"""
from __future__ import annotations

import socketio

# Socket.IO 子路径（服务端、客户端必须一致）。
# 与 WS_EVENTS §0.2「ws://localhost:8000/ws」对齐 —— ASGIApp 实际暴露 /ws/?EIO=4&transport=...
SOCKETIO_PATH = "ws"

# AsyncServer 单例。
# - cors_allowed_origins 与 FastAPI CORSMiddleware 一致
# - ping_interval / ping_timeout 对齐 WS_EVENTS §0.3
# - logger / engineio_logger 默认关闭，避免淹没日志；调试时可开
sio: socketio.AsyncServer = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["http://localhost:5173"],
    ping_interval=25,
    ping_timeout=60,
    logger=False,
    engineio_logger=False,
)
