import { defineConfig } from 'vitest/config'

// Config kept separate from vite.config.ts (which pulls in the vue plugin and
// proxies, useless here): the tests only cover pure functions, default node env.
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
  },
})
