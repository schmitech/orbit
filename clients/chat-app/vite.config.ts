import { defineConfig, loadEnv, type ViteDevServer } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { adaptersPlugin } from './vite-plugin-adapters';

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
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const useLocalApi = env.VITE_USE_LOCAL_API === 'true';
  const enableMiddleware = env.VITE_ENABLE_API_MIDDLEWARE === 'true';

  const localApiDir = useLocalApi
    ? path.resolve(__dirname, '../node-api/dist')
    : path.resolve(__dirname, 'src/api/local-stub');

  const plugins: any[] = [react(), fixMaxListenersPlugin()];
  
  // Add adapters plugin when middleware is enabled
  if (enableMiddleware) {
    plugins.push(adaptersPlugin());
  }

  return {
    plugins,
    optimizeDeps: {
      exclude: [
        'lucide-react',
        '@schmitech/chatbot-api',
        '@schmitech/markdown-renderer',
      ],
    },
    resolve: {
      alias: {
        // Alias for local node-api package during development
        '@local-node-api': localApiDir,
      },
    },
    server: {
      fs: {
        // Allow serving files from the parent clients directory
        // This enables importing from ../node-api/dist during local development
        allow: [
          // Search up for workspace root
          path.resolve(__dirname, '..'),
        ],
      },
      proxy: enableMiddleware && env.VITE_MIDDLEWARE_SERVER_URL ? {
        // Proxy API proxy requests to Express server when middleware is enabled
        '/api/proxy': {
          target: env.VITE_MIDDLEWARE_SERVER_URL,
          changeOrigin: true,
          ws: false,
        },
      } : undefined,
    },
  };
});
