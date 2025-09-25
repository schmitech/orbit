# Local API Testing

This document explains how to test the chat-app with the local API dist build before publishing the npm package.

## Overview

The chat-app now supports loading the API from either:
1. **NPM Package** (default) - Uses the published `@schmitech/chatbot-api` package
2. **Local Dist Build** - Uses the local `../node-api/dist` build for testing

## Environment Variables

Add these to your `.env` file:

```bash
# Set to 'true' to use local dist build instead of npm package
VITE_USE_LOCAL_API=false

# Path to local API dist (relative to chat-app directory)
VITE_LOCAL_API_PATH=../node-api/dist
```

## Available Scripts

### Development
```bash
# Use npm package (default)
npm run dev

# Use local dist build
npm run dev:local

# Build API and use local dist
npm run dev:with-api
```

### Building
```bash
# Build with npm package (default)
npm run build

# Build with local dist
npm run build:local

# Build API first, then build app with local dist
npm run build:api && npm run build:local
```

### Preview
```bash
# Preview with npm package (default)
npm run preview

# Preview with local dist
npm run preview:local
```

## Testing Workflow

### 1. Test with Local API
```bash
# 1. Build the node-api package
cd ../node-api
npm run build

# 2. Start the chat-app with local API
cd ../chat-app
npm run dev:local
```

### 2. Test with NPM Package
```bash
# 1. Publish the package (if needed)
cd ../node-api
npm publish

# 2. Update package.json in chat-app
cd ../chat-app
npm install @schmitech/chatbot-api@latest

# 3. Start with npm package
npm run dev
```

## How It Works

The app uses a dynamic API loader (`src/api/loader.ts`) that:

1. **Checks Environment**: Reads `VITE_USE_LOCAL_API` to determine which API to load
2. **Loads API**: Dynamically imports either the local dist or npm package
3. **Fallback**: If local loading fails, automatically falls back to npm package
4. **Caching**: Caches the loaded API to avoid repeated imports

## File Structure

```
clients/
├── chat-app/
│   ├── src/
│   │   ├── api/
│   │   │   └── loader.ts          # Dynamic API loader
│   │   └── stores/
│   │       └── chatStore.ts       # Updated to use dynamic loader
│   ├── .env                       # Environment variables
│   └── package.json               # Updated scripts
└── node-api/
    ├── dist/                      # Built API files
    └── package.json
```

## Troubleshooting

### Local API Not Loading
- Ensure `../node-api/dist` exists and contains built files
- Check that `VITE_USE_LOCAL_API=true` is set
- Verify the path in `VITE_LOCAL_API_PATH` is correct

### Fallback to NPM Package
- The app will automatically fall back to npm package if local loading fails
- Check console for error messages about API loading

### Build Issues
- Make sure to run `npm run build` in the node-api directory first
- Check that all TypeScript compilation passes

## Benefits

1. **Test Before Publish**: Test API changes without publishing to npm
2. **Faster Iteration**: No need to publish/test/publish cycle
3. **Safe Fallback**: Automatically falls back to npm package if local fails
4. **Easy Switching**: Simple environment variable to switch between modes
