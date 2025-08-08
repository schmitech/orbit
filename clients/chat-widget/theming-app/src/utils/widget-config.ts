// Widget source configuration
interface WidgetUrls {
  jsUrl: string;
  cssUrl: string;
  isLocal: boolean;
}

interface WidgetConfig {
  source: 'local' | 'npm';
  debug: boolean;
  promptEnabled: boolean;
  defaultApiEndpoint: string;
  github: {
    owner: string;
    repo: string;
  };
  npm: {
    version: string;
    jsUrl: (version: string) => string;
    cssUrl: (version: string) => string;
  };
  local: {
    jsPath: string;
    cssPath: string;
  };
}

export const WIDGET_CONFIG: WidgetConfig = {
  // Toggle between 'local' and 'npm'
  source: (import.meta.env.VITE_WIDGET_SOURCE as 'local' | 'npm') || 'npm',
  
  // Debug logging - automatically disabled in production, can be overridden
  debug: import.meta.env.VITE_WIDGET_DEBUG === 'false' 
    ? false 
    : (import.meta.env.VITE_WIDGET_DEBUG === 'true' || import.meta.env.DEV),
  
  // Prompt tab enabled/disabled
  promptEnabled: import.meta.env.VITE_PROMPT_ENABLED !== 'false',
  
  // Default API endpoint
  defaultApiEndpoint: import.meta.env.VITE_DEFAULT_API_ENDPOINT || 'http://localhost:3000',
  
  // GitHub configuration
  github: {
    owner: import.meta.env.VITE_GITHUB_OWNER || 'schmitech',
    repo: import.meta.env.VITE_GITHUB_REPO || 'orbit'
  },
  
  // NPM configuration
  npm: {
    version: import.meta.env.VITE_NPM_WIDGET_VERSION || '0.4.9',
    jsUrl: (version: string) => `https://unpkg.com/@schmitech/chatbot-widget@${version}/dist/chatbot-widget.umd.js`,
    cssUrl: (version: string) => `https://unpkg.com/@schmitech/chatbot-widget@${version}/dist/chatbot-widget.css`
  },
  
  // Local configuration - try multiple possible paths
  local: {
    // Theming app is in subdirectory, so needs ../dist/ (different from demo.html)
    jsPath: import.meta.env.VITE_LOCAL_WIDGET_JS_PATH || '../dist/chatbot-widget.umd.js',
    cssPath: import.meta.env.VITE_LOCAL_WIDGET_CSS_PATH || '../dist/chatbot-widget.css'
  }
};

// Helper function to get current widget URLs
export const getWidgetUrls = (): WidgetUrls => {
  const config = WIDGET_CONFIG;
  
  if (config.source === 'local') {
    return {
      jsUrl: config.local.jsPath,
      cssUrl: config.local.cssPath,
      isLocal: true
    };
  } else {
    return {
      jsUrl: config.npm.jsUrl(config.npm.version),
      cssUrl: config.npm.cssUrl(config.npm.version),
      isLocal: false
    };
  }
};

// Helper function to check if debug logging is enabled
export const isDebugEnabled = (): boolean => {
  return WIDGET_CONFIG.debug;
};

// Helper function to get possible local paths for troubleshooting
export const getPossibleLocalPaths = () => {
  return {
    // Demo.html style (same directory level)
    sameLevel: {
      js: './dist/chatbot-widget.umd.js',
      css: './dist/chatbot-widget.css'
    },
    // Theming app style (one level up)
    oneUp: {
      js: '../dist/chatbot-widget.umd.js',
      css: '../dist/chatbot-widget.css'
    },
    // Absolute from widget root
    absolute: {
      js: '/clients/chat-widget/dist/chatbot-widget.umd.js',
      css: '/clients/chat-widget/dist/chatbot-widget.css'
    }
  };
}; 