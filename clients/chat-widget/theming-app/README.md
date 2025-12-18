# Widget Source Toggle & Theming App Guide

## Quick Start

### Using NPM Package (Default)
```bash
npm run dev
# or specifically
npm run dev:npm
```

### Using Local Build
```bash
npm run dev:local
```

## Environment Variables

You can configure the widget source using environment variables:

### Available Variables

```bash
# Widget source toggle - 'local' or 'npm'
VITE_WIDGET_SOURCE=local

# Debug logging toggle - 'true', 'false', or auto (defaults to DEV mode)
VITE_WIDGET_DEBUG=true

# Local widget paths (used when VITE_WIDGET_SOURCE=local)
VITE_LOCAL_WIDGET_JS_PATH=../dist/chatbot-widget.umd.js
VITE_LOCAL_WIDGET_CSS_PATH=../dist/chatbot-widget.css

# NPM widget version (used when VITE_WIDGET_SOURCE=npm)
VITE_NPM_WIDGET_VERSION=0.4.9
```

### Debug Logging Behavior

The debug logging follows this priority:
1. **Production builds**: Debug logging is **automatically disabled** (`import.meta.env.DEV = false`)
2. **Development builds**: Debug logging is **enabled by default** (`import.meta.env.DEV = true`)
3. **Manual override**: Set `VITE_WIDGET_DEBUG=false` to disable even in development
4. **Force enable**: Set `VITE_WIDGET_DEBUG=true` to enable even in production (not recommended)

### Setting Up Environment Variables

Create a `.env.local` file in the theming app root:

```bash
# .env.local

# Widget source
VITE_WIDGET_SOURCE=local

# Debug logging (optional - defaults to development mode)
VITE_WIDGET_DEBUG=true

# Prompt tab configuration (optional - defaults to enabled)
VITE_PROMPT_ENABLED=true

# Default API endpoint (optional - defaults to localhost:3000)
VITE_DEFAULT_API_ENDPOINT=http://localhost:3000

# GitHub repository configuration (optional - defaults to schmitech/orbit)
VITE_GITHUB_OWNER=schmitech
VITE_GITHUB_REPO=orbit

# Paths
VITE_LOCAL_WIDGET_JS_PATH=../dist/chatbot-widget.umd.js
VITE_LOCAL_WIDGET_CSS_PATH=../dist/chatbot-widget.css
VITE_NPM_WIDGET_VERSION=0.4.9
```

## Debug Logging Examples

### Development Mode (Debug Enabled)
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 WIDGET SOURCE: 🔧 LOCAL BUILD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 JavaScript: ../dist/chatbot-widget.umd.js
🎨 Stylesheet: ../dist/chatbot-widget.css
💡 Using local build - ensure widget is compiled in ../dist/
⚡ To switch to NPM: npm run dev:npm
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Widget loaded successfully from LOCAL BUILD!

🚀 INITIALIZING WIDGET WITH 🔧 LOCAL BUILD
📋 Widget Configuration:
   Header: "AI Assistant"
   Welcome: "Hello! How can I help you today?"
   Suggested Questions: 2 items
   Primary Color: #EC994B
   Secondary Color: #1E3A8A
✅ Widget initialized successfully with 🔧 LOCAL BUILD!
🎯 Widget ready for testing in bottom-right corner
```

### Production Mode (Debug Disabled)
```
# Silent operation - no debug logs
# Only critical errors are shown
```

### Debug Disabled in Development
```bash
# Set in .env.local
VITE_WIDGET_DEBUG=false
```
Result: Silent operation even in development mode.

## Usage Scenarios

### 1. Testing Local Changes Before Publishing

When you've made changes to the widget and want to test them:

```bash
# 1. Build the widget locally (from widget root directory)
npm run build

# 2. Test with local build (from theming app directory)
npm run dev:local
```

### 2. Testing Against Published NPM Package

To ensure compatibility with the current published version:

```bash
npm run dev:npm
```

### 3. Production Deployments

For production, debug logging is automatically disabled regardless of `VITE_WIDGET_SOURCE`:

```bash
# Build for production with NPM package (recommended)
npm run build:npm

# Build for production with local version (for internal deployments)
npm run build:local
```

Both will have debug logging disabled in production.

### 4. Prompt Tab Configuration

The prompt tab allows users to customize the system prompt for their chatbot. You can disable this feature in production if it's not ready:

```bash
# Disable prompt tab functionality
VITE_PROMPT_ENABLED=false
```

When disabled:
- The "Prompt" tab will not appear in the navigation
- If a user is on the prompt tab when disabled, they'll be redirected to the "Theme" tab
- The prompt functionality will be completely hidden from the UI

### 5. API Endpoint Configuration

You can set a default API endpoint that will pre-populate the API endpoint field:

```bash
# Set default API endpoint
VITE_DEFAULT_API_ENDPOINT=https://your-production-api.com
```

This is useful for:
- Pre-configuring production endpoints for different environments
- Setting up staging vs production endpoints
- Providing a default that users can modify

### 6. GitHub Repository Configuration

You can configure which GitHub repository to display stats for:

```bash
# Set GitHub repository for stats display
VITE_GITHUB_OWNER=schmitech
VITE_GITHUB_REPO=orbit
```

This is useful for:
- Displaying stats for your own fork of the project
- Pointing to different repositories for different deployments
- Customizing the "Powered by" section for your own projects

### 7. Clean Development (No Debug Logs)

If you want development without verbose logging:

```bash
# Option 1: Environment variable
VITE_WIDGET_DEBUG=false npm run dev:local

# Option 2: Set in .env.local
echo "VITE_WIDGET_DEBUG=false" >> .env.local
npm run dev:local
```

## Visual Indicators

The theming app displays a badge in the header indicating which source is being used:

- 🔧 **Local Build** - Green badge when using local files
- 📦 **NPM Package** - Blue badge when using NPM package

## Troubleshooting

### Local Build Not Loading

If you see errors when using local build:

1. **Check if widget is built**: Make sure you've run `npm run build` in the widget directory
2. **Verify paths**: Ensure the paths in your environment variables point to the correct files
3. **Check console**: Look for loading errors in browser developer tools
4. **Enable debug logging**: Set `VITE_WIDGET_DEBUG=true` for detailed troubleshooting

### Path Configuration

The default paths assume this directory structure:
```
orbit/
├── clients/
│   └── chat-widget/
│       ├── dist/                    # Widget build output
│       │   ├── chatbot-widget.umd.js
│       │   └── chatbot-widget.css
│       └── theming-app/             # This app
│           └── ...
```

If your structure is different, adjust the `VITE_LOCAL_WIDGET_*_PATH` variables accordingly.

## Integration with Build Pipeline

For automated testing, you can use environment variables in your CI/CD:

```yaml
# Example GitHub Actions
- name: Test with local build (debug enabled)
  run: npm run dev:local
  env:
    VITE_WIDGET_SOURCE: local
    VITE_WIDGET_DEBUG: true

- name: Test with NPM package (debug disabled)
  run: npm run dev:npm
  env:
    VITE_WIDGET_SOURCE: npm
    VITE_WIDGET_DEBUG: false

- name: Production build (debug auto-disabled)
  run: npm run build:npm
```

## Development Workflow

Recommended workflow for widget development:

1. **Make changes** to the widget source code
2. **Build the widget**: `npm run build` (from widget directory)
3. **Test locally with debug**: `npm run dev:local` (from theming app)
4. **Verify functionality** in the theming app
5. **Test with NPM**: `npm run dev:npm` to ensure compatibility
6. **Disable debug for clean testing**: `VITE_WIDGET_DEBUG=false npm run dev:local`
7. **Test production build**: `npm run build:local` (debug auto-disabled)
8. **Publish widget** when satisfied
9. **Update version** in environment variables if needed

## Error Handling

- **Critical errors** (load failures, initialization errors) are always shown, even in production
- **Debug information** and **troubleshooting tips** are only shown when debug is enabled
- **Widget source indicators** are always shown in the UI, regardless of debug setting