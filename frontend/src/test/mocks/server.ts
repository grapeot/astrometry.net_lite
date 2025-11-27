import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// Create MSW server instance
export const server = setupServer(...handlers)
