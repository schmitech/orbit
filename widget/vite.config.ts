import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import dts from 'vite-plugin-dts';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Function to check for a custom config file and use it if it exists
const getCustomConfigPlugin = () => {
  return {
    name: 'vite-plugin-custom-chat-config',
    buildStart() {
      const customConfigPath = process.env.CHAT_CONFIG_PATH || './custom-chat-config.json';
      
      if (fs.existsSync(customConfigPath)) {
        console.log(`Using custom chat configuration from: ${customConfigPath}`);
        const customConfig = fs.readFileSync(customConfigPath, 'utf-8');
        
        // Ensure the directory exists
        if (!fs.existsSync('./src/config')) {
          fs.mkdirSync('./src/config', { recursive: true });
        }
        
        // Write the custom config to the source directory
        fs.writeFileSync('./src/config/chatConfig.json', customConfig);
      } else {
        console.log('No custom chat configuration found, using defaults.');
      }
    }
  };
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    getCustomConfigPlugin(),
    react(),
    dts({
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      exclude: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
      rollupTypes: true,
      insertTypesEntry: true,
      beforeWriteFile: (filePath, content) => ({
        filePath: filePath.replace('/src/', '/'),
        content
      })
    })
  ],
  define: {
    'process.env': JSON.stringify({
      NODE_ENV: 'production'
    }),
    // Ensure these global variables are recognized in UMD build
    'window.React': 'React',
    'window.ReactDOM': 'ReactDOM'
  },
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'ChatbotWidget',
      formats: ['es', 'umd'],
      fileName: (format) => `chatbot-widget.${format}.js`
    },
    rollupOptions: {
      external: ['react', 'react-dom'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM'
        },
        // Don't split code for UMD builds
        manualChunks: undefined
      }
    },
    sourcemap: true,
    cssCodeSplit: false,
    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true
    },
    // Exclude demo.html from the build output
    emptyOutDir: true,
    copyPublicDir: false
  }
});
