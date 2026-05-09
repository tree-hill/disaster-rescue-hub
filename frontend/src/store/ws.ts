/**
 * WebSocket / Socket.IO Store（P7.2）。
 *
 * 对照：
 * - WS_EVENTS §0.2 认证：auth dict {token} 优先，回退 query ?token=
 * - WS_EVENTS §0.4 房间：commander / admin
 * - WS_EVENTS §2 welcome / auth_error / subscribed / subscribe_error
 * - backend/app/ws/handlers.py：subscribe / unsubscribe payload = {rooms: string[]}
 *
 * 设计：
 * - 单例 socket：同一 store，避免双连接
 * - 登录后 connect() → 自动重连（reconnectionAttempts=MAX_RECONNECT，1s 起，封顶 5s）
 * - rooms 是 store 状态：重连成功后用 socket.emit('subscribe', {rooms}) 把上次房间重订
 * - addListener / removeListener：组件 useEffect 内挂监听器，卸载时清理
 * - logout 调 disconnect() 释放连接
 */
import { io, Socket } from 'socket.io-client';
import { create } from 'zustand';

import { MAX_RECONNECT } from '@/constants';
import { useAuthStore } from '@/store/auth';

export type WSEventName =
  | 'welcome'
  | 'auth_error'
  | 'subscribed'
  | 'subscribe_error'
  | 'kpi.snapshot'
  | 'alert.raised'
  | 'alert.acknowledged'
  | 'alert.ignored'
  | 'task.created'
  | 'task.cancelled'
  | 'task.reassigned'
  | 'auction.started'
  | 'auction.bid_submitted'
  | 'auction.completed'
  | 'auction.failed'
  | 'dispatch.algorithm_changed'
  | 'intervention.recorded'
  | 'blackboard.updated'
  | 'perception.detection'
  | 'perception.high_confidence_alert'
  | 'robot.fault_occurred'
  | 'robot.recall_initiated'
  | 'robot.recall_completed'
  | 'robot.state_changed';

interface WSState {
  socket: Socket | null;
  connected: boolean;
  rooms: string[];
  /** 建立连接（如未建立）。token 从 useAuthStore 实时读取，避免握手时 token 已轮换。 */
  connect: () => void;
  /** 主动断开。logout 时调用。 */
  disconnect: () => void;
  /** 加入一组房间；服务端 subscribe 失败会单独 emit subscribe_error，房间状态以本地累加为准。 */
  subscribe: (...rooms: string[]) => void;
  /** 退订一组房间。 */
  unsubscribe: (...rooms: string[]) => void;
  /** 监听服务端事件；返回 unsubscribe handler。组件 useEffect 中调用。 */
  addListener: <P = unknown>(name: WSEventName, handler: (payload: P) => void) => () => void;
}

export const useWSStore = create<WSState>((set, get) => ({
  socket: null,
  connected: false,
  rooms: [],
  connect: () => {
    if (get().socket) return;
    const socket = io({
      path: '/socket.io',
      transports: ['websocket'],
      auth: (cb) => {
        // socket.io-client 支持函数式 auth：每次握手时拉取最新 token（过期重连/刷新后仍正确）
        cb({ token: useAuthStore.getState().accessToken ?? '' });
      },
      reconnection: true,
      reconnectionAttempts: MAX_RECONNECT,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    socket.on('connect', () => {
      set({ connected: true });
      // 重连后把上次房间重新订上
      const rooms = get().rooms;
      if (rooms.length > 0) {
        socket.emit('subscribe', { rooms });
      }
    });

    socket.on('disconnect', () => set({ connected: false }));

    socket.on('auth_error', (payload: { reason?: string }) => {
      // token 失效 → 清空登录态，跳登录页
      // eslint-disable-next-line no-console
      console.warn('[ws] auth_error', payload?.reason);
      useAuthStore.getState().clear();
      get().disconnect();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    });

    set({ socket });
  },
  disconnect: () => {
    const s = get().socket;
    if (s) {
      s.removeAllListeners();
      s.disconnect();
    }
    set({ socket: null, connected: false, rooms: [] });
  },
  subscribe: (...rooms) => {
    const next = Array.from(new Set([...get().rooms, ...rooms]));
    set({ rooms: next });
    const s = get().socket;
    if (s && s.connected && rooms.length > 0) {
      s.emit('subscribe', { rooms });
    }
  },
  unsubscribe: (...rooms) => {
    const set_ = new Set(get().rooms);
    rooms.forEach((r) => set_.delete(r));
    set({ rooms: Array.from(set_) });
    const s = get().socket;
    if (s && s.connected && rooms.length > 0) {
      s.emit('unsubscribe', { rooms });
    }
  },
  addListener: (name, handler) => {
    const s = get().socket;
    if (!s) {
      // eslint-disable-next-line no-console
      console.warn('[ws] addListener called before connect()');
      return () => undefined;
    }
    s.on(name, handler as (...args: unknown[]) => void);
    return () => {
      s.off(name, handler as (...args: unknown[]) => void);
    };
  },
}));
