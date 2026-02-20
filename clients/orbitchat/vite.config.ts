import { defineConfig, type ViteDevServer, type PluginOption } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { orbitchatConfigPlugin } from './vite-plugin-orbitchat-config';

// Plugin to fix MaxListenersExceededWarning in development
// Vite's HMR can add multiple close listeners
const fixMaxListenersPlugin = () => ({
  name: 'fix-max-listeners',
  configureServer(server: ViteDevServer) {
    // Increase max listeners to prevent warning during HMR
    if (server.httpServer) {
      server.httpServer.setMaxListeners(20);
    }
  },
});

// https://vitejs.dev/config/
export default defineConfig(() => {
  const plugins: PluginOption[] = [react(), fixMaxListenersPlugin(), orbitchatConfigPlugin()];

  return {
    plugins,
    optimizeDeps: {
      exclude: [
        'lucide-react',
      ],
    },
    resolve: {
      alias: {
        // Markdown renderer alias (always needed)
        '@schmitech/markdown-renderer': path.resolve(__dirname, 'markdown-renderer/src/index.ts'),
        '@schmitech/markdown-renderer/styles': path.resolve(__dirname, 'markdown-renderer/src/MarkdownStyles.css'),
      },
    },
    server: {
      fs: {
        allow: [
          path.resolve(__dirname, '..'),
        ],
      },
    },
  };
});
