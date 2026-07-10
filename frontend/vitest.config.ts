import { defineConfig } from 'vitest/config'

// Config separata da vite.config.ts (che porta plugin vue e proxy inutili qui):
// i test coprono solo funzioni pure, ambiente node di default.
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
  },
})
