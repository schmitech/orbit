import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const useLocalApi = env.VITE_USE_LOCAL_API === 'true';

  const localApiDir = useLocalApi
    ? path.resolve(__dirname, '../node-api/dist')
    : path.resolve(__dirname, 'src/api/local-stub');

  return {
    plugins: [react()],
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
    },
  };
});
