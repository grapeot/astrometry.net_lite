import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Detect if running in Docker environment
const isDocker = process.env.DOCKER_ENV === 'true'

// Get port from environment variable, default to 5173
const frontendPort = parseInt(process.env.VITE_FRONTEND_PORT || process.env.FRONTEND_PORT || '5173', 10)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Docker environment needs to listen on 0.0.0.0, local development uses localhost
    host: isDocker ? '0.0.0.0' : 'localhost',
    port: frontendPort,
    strictPort: true,
    // Use polling only in Docker environment
    watch: isDocker ? {
      usePolling: true,
      interval: 2000,
    } : undefined,
    // HMR config: Docker environment needs to specify clientPort, local uses default config (not set)
    ...(isDocker ? {
      hmr: {
        clientPort: frontendPort,
      },
    } : {}),
    fs: {
      strict: false,
    },
  },
  optimizeDeps: {
    // Pre-build dependencies to avoid runtime lag
    include: ['react', 'react-dom', 'react-router-dom'],
  },
})
