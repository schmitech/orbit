import { readFileSync } from 'node:fs';
import { defineConfig } from 'tsup';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string };

export default defineConfig({
  entry: ['src/cli.ts'],
  format: ['esm'],
  target: 'node20',
  platform: 'node',
  clean: true,
  sourcemap: true,
  dts: false,
  // Baked in at build time rather than read from package.json at runtime, so
  // --version works the same whether run from a source checkout or a global
  // npm install (no relative-path lookup back to a package.json to get wrong).
  define: {
    __ORBIT_CLI_VERSION__: JSON.stringify(pkg.version),
  },
});
