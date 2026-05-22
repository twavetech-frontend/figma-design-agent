import { defineConfig } from 'tsup'

export default defineConfig({
  entry: {
    'bridge/index': 'src/bridge/index.ts',
    'yoga-cli/index': 'src/yoga-cli.ts',
  },
  format: ['cjs'],
  outDir: 'out',
  target: 'node18',
  sourcemap: true,
  minify: false,
  splitting: false,
  clean: true,
  dts: false,
  // Externalize native/Node modules that can't be bundled
  external: [
    'ws',
    'bufferutil',
    'utf-8-validate',
    'yoga-layout',
  ],
  // Do NOT use noExternal — let tsup auto-resolve which deps to bundle
})
