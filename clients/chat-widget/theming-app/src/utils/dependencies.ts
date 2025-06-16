import { getWidgetUrls, isDebugEnabled, getPossibleLocalPaths } from './widget-config';

interface LoadDependencyResult {
  success: boolean;
  url?: string;
  error?: string;
}

// Track loaded scripts and stylesheets to prevent duplicates
const loadedScripts = new Set<string>();
const loadedStylesheets = new Set<string>();

const debugLog = (...args: any[]) => {
  if (isDebugEnabled()) {
    console.log(
      '%c🔧 Widget Loader:', 
      'background: #2563eb; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold;',
      ...args
    );
  }
};

const debugError = (...args: any[]) => {
  console.error(
    '%c❌ Widget Loader Error:', 
    'background: #dc2626; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold;',
    ...args
  );
};

// Enhanced script loader with fallback paths for local builds
async function loadScript(src: string, isLocal: boolean = false): Promise<LoadDependencyResult> {
  // Prevent duplicate loading
  if (loadedScripts.has(src)) {
    debugLog(`Script already loaded: ${src}`);
    return { success: true, url: src };
  }

  // For local builds, try multiple paths like demo.html
  if (isLocal) {
    const possiblePaths = getPossibleLocalPaths();
    const pathsToTry = [
      src, // Original path
      possiblePaths.sameLevel.js, // Demo.html style
      possiblePaths.oneUp.js, // Original theming app style
      possiblePaths.absolute.js // Absolute path
    ];

    for (const pathToTry of pathsToTry) {
      debugLog(`Trying local script path: ${pathToTry}`);
      
      try {
        const result = await loadSingleScript(pathToTry, true);
        if (result.success) {
          debugLog(`✅ Successfully loaded local script: ${pathToTry}`);
          loadedScripts.add(src);
          return result;
        }
      } catch (error) {
        debugLog(`❌ Failed to load script from: ${pathToTry}`, error);
      }
    }
    
    debugError(`Failed to load local script from any path. Tried:`, pathsToTry);
    return { 
      success: false, 
      error: `Failed to load local script. Tried paths: ${pathsToTry.join(', ')}` 
    };
  }

  // For NPM builds, just load directly
  return loadSingleScript(src, false);
}

async function loadSingleScript(src: string, isLocal: boolean): Promise<LoadDependencyResult> {
  return new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = isLocal ? `${src}?t=${Date.now()}` : src; // Cache busting for local files
    script.crossOrigin = 'anonymous';

    script.onload = () => {
      debugLog(`✅ Script loaded successfully: ${src}`);
      loadedScripts.add(src);
      resolve({ success: true, url: src });
    };

    script.onerror = () => {
      debugError(`❌ Failed to load script: ${src}`);
      resolve({ 
        success: false, 
        error: `Failed to load script: ${src}` 
      });
    };

    document.head.appendChild(script);
  });
}

// Enhanced CSS loader with fallback paths for local builds
async function loadStylesheet(href: string, isLocal: boolean = false): Promise<LoadDependencyResult> {
  // Prevent duplicate loading
  if (loadedStylesheets.has(href)) {
    debugLog(`Stylesheet already loaded: ${href}`);
    return { success: true, url: href };
  }

  // For local builds, try multiple paths like demo.html
  if (isLocal) {
    const possiblePaths = getPossibleLocalPaths();
    const pathsToTry = [
      href, // Original path
      possiblePaths.sameLevel.css, // Demo.html style
      possiblePaths.oneUp.css, // Original theming app style
      possiblePaths.absolute.css // Absolute path
    ];

    for (const pathToTry of pathsToTry) {
      debugLog(`Trying local CSS path: ${pathToTry}`);
      
      try {
        const result = await loadSingleStylesheet(pathToTry, true);
        if (result.success) {
          debugLog(`✅ Successfully loaded local CSS: ${pathToTry}`);
          loadedStylesheets.add(href);
          return result;
        }
      } catch (error) {
        debugLog(`❌ Failed to load CSS from: ${pathToTry}`, error);
      }
    }
    
    debugError(`Failed to load local CSS from any path. Tried:`, pathsToTry);
    return { 
      success: false, 
      error: `Failed to load local CSS. Tried paths: ${pathsToTry.join(', ')}` 
    };
  }

  // For NPM builds, just load directly
  return loadSingleStylesheet(href, false);
}

async function loadSingleStylesheet(href: string, isLocal: boolean): Promise<LoadDependencyResult> {
  return new Promise((resolve) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = isLocal ? `${href}?t=${Date.now()}` : href; // Cache busting for local files

    link.onload = () => {
      debugLog(`✅ Stylesheet loaded successfully: ${href}`);
      loadedStylesheets.add(href);
      resolve({ success: true, url: href });
    };

    link.onerror = () => {
      debugError(`❌ Failed to load stylesheet: ${href}`);
      resolve({ 
        success: false, 
        error: `Failed to load stylesheet: ${href}` 
      });
    };

    document.head.appendChild(link);
  });
}

// Check if React is available (like demo.html does)
function checkReactAvailability(): boolean {
  const hasReact = typeof window.React !== 'undefined';
  const hasReactDOM = typeof window.ReactDOM !== 'undefined';
  
  debugLog(`React availability check:`, {
    React: hasReact,
    ReactDOM: hasReactDOM
  });
  
  return hasReact && hasReactDOM;
}

// Main dependency loader function (matches demo.html approach)
export async function loadWidgetDependencies(): Promise<{ success: boolean; errors: string[] }> {
  const urls = getWidgetUrls();
  const errors: string[] = [];
  
  debugLog('🚀 Starting widget dependency loading...');
  debugLog('📊 Widget Configuration:', {
    source: urls.isLocal ? 'Local Build' : 'NPM Package',
    jsUrl: urls.jsUrl,
    cssUrl: urls.cssUrl,
    debugEnabled: isDebugEnabled()
  });

  // Step 1: Check React availability (like demo.html)
  if (!checkReactAvailability()) {
    const reactError = 'React and ReactDOM must be loaded first (like in demo.html)';
    debugError(reactError);
    errors.push(reactError);
    return { success: false, errors };
  }

  debugLog('✅ React and ReactDOM are available');

  try {
    // Step 2: Load CSS first (like demo.html does)
    debugLog(`🎨 Loading CSS from: ${urls.cssUrl}`);
    const cssResult = await loadStylesheet(urls.cssUrl, urls.isLocal);
    if (!cssResult.success) {
      errors.push(cssResult.error || 'Failed to load CSS');
    }

    // Step 3: Load JavaScript (like demo.html does)
    debugLog(`📦 Loading JavaScript from: ${urls.jsUrl}`);
    const jsResult = await loadScript(urls.jsUrl, urls.isLocal);
    if (!jsResult.success) {
      errors.push(jsResult.error || 'Failed to load JavaScript');
    }

    // Step 4: Verify widget is available (like demo.html checks)
    const hasWidget = typeof window.initChatbotWidget === 'function';
    const hasChatbotWidget = typeof window.ChatbotWidget === 'object';
    
    debugLog('🔍 Widget availability check:', {
      initChatbotWidget: hasWidget,
      ChatbotWidget: hasChatbotWidget
    });

    if (!hasWidget) {
      const widgetError = 'initChatbotWidget function not found after loading';
      debugError(widgetError);
      errors.push(widgetError);
    }

    const success = errors.length === 0;
    
    if (success) {
      debugLog('🎉 All dependencies loaded successfully!');
      debugLog('📋 Ready to initialize widget with initChatbotWidget()');
    } else {
      debugError('❌ Failed to load some dependencies:', errors);
      debugLog('💡 Troubleshooting tips:');
      debugLog('  1. Check browser Network tab for 404 errors');
      debugLog('  2. Verify build files exist: npm run widget:check');
      debugLog('  3. Try hard refresh: Ctrl+Shift+R / Cmd+Shift+R');
      if (urls.isLocal) {
        debugLog('  4. Rebuild widget: cd ../.. && npm run build');
        debugLog('  5. Check paths match demo.html structure');
      }
    }

    return { success, errors };

  } catch (error) {
    const errorMsg = `Unexpected error loading dependencies: ${error}`;
    debugError(errorMsg);
    errors.push(errorMsg);
    return { success: false, errors };
  }
}

// Export for debugging
export const getDependencyStatus = () => ({
  loadedScripts: Array.from(loadedScripts),
  loadedStylesheets: Array.from(loadedStylesheets),
  config: getWidgetUrls()
});

// Load Prism.js for syntax highlighting in code tab
export async function loadPrism(): Promise<void> {
  // Check if Prism is already loaded
  if (typeof window.Prism !== 'undefined') {
    debugLog('✅ Prism.js already loaded');
    return;
  }

  debugLog('📦 Loading Prism.js for syntax highlighting...');

  try {
    // Load Prism CSS
    await loadSingleStylesheet('https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css', false);
    
    // Load Prism JS
    await loadSingleScript('https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js', false);
    
    // Load additional language support
    await loadSingleScript('https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-javascript.min.js', false);
    await loadSingleScript('https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-typescript.min.js', false);
    await loadSingleScript('https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-jsx.min.js', false);
    
    debugLog('✅ Prism.js loaded successfully');
  } catch (error) {
    debugError('❌ Failed to load Prism.js:', error);
    throw error;
  }
}