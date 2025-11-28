import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      // 在 Docker 中使用 polling 模式，确保文件变化能被检测到
      usePolling: true,
      interval: 1000,
    },
  },
})
