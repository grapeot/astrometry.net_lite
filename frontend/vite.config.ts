import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 检测是否在 Docker 环境中运行
const isDocker = process.env.DOCKER_ENV === 'true'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Docker 环境需要监听 0.0.0.0，本地开发使用 localhost
    host: isDocker ? '0.0.0.0' : 'localhost',
    port: 5173,
    strictPort: true,
    // 只在 Docker 环境中使用 polling
    watch: isDocker ? {
      usePolling: true,
      interval: 2000,
    } : undefined,
    // HMR 配置：Docker 环境需要指定 clientPort，本地使用默认配置（不设置）
    ...(isDocker ? {
      hmr: {
        clientPort: 5173,
      },
    } : {}),
    fs: {
      strict: false,
    },
  },
  optimizeDeps: {
    // 预构建依赖，避免运行时卡顿
    include: ['react', 'react-dom', 'react-router-dom'],
  },
})
