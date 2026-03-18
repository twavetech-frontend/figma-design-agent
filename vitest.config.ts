import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    globals: false,
    // yoga-layout is ESM; vitest needs to transform it for CJS compatibility
    server: {
      deps: {
        inline: ['yoga-layout'],
      },
    },
  },
});
