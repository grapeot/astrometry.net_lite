import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: {
      // 在 Docker 中使用 polling 模式，确保文件变化能被检测到
      usePolling: true,
      interval: 2000, // 增加轮询间隔，减少性能开销
    },
    hmr: {
      clientPort: 5173,
    },
    // 优化 Docker 环境中的性能
    fs: {
      strict: false,
    },
  },
  optimizeDeps: {
    // 强制预构建，避免运行时卡顿
    force: false,
  },
})
