import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    // 注意：Windows Hyper-V 把 TCP 5109-5208（含默认 5173）保留了，绑定会 EACCES。
    // 改用 5500，并锁 IPv4 + strictPort 防止意外漂移。
    host: '127.0.0.1',
    port: 5500,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
