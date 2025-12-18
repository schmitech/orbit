#!/usr/bin/env node

import fs from 'fs';
import path from 'path';

// Test multiple possible paths (like demo.html vs theming-app structure)
const POSSIBLE_PATHS = {
  // Demo.html style (same level as demo.html)
  sameLevel: {
    js: './dist/chatbot-widget.umd.js',
    css: './dist/chatbot-widget.css'
  },
  // Theming app style (one level up)
  oneUp: {
    js: '../dist/chatbot-widget.umd.js',
    css: '../dist/chatbot-widget.css'
  },
  // Alternative absolute paths
  absolute: {
    js: '../dist/chatbot-widget.umd.js', // Most likely correct
    css: '../dist/chatbot-widget.css'
  }
};

function checkFile(filePath, name) {
  console.log(`\n🔍 Checking ${name}:`);
  
  if (!fs.existsSync(filePath)) {
    console.log(`❌ File not found: ${filePath}`);
    return false;
  }
  
  const stats = fs.statSync(filePath);
  const sizeKB = Math.round(stats.size / 1024);
  const lastModified = new Date(stats.mtime);
  const now = new Date();
  const ageMinutes = Math.round((now - lastModified) / (1000 * 60));
  
  console.log(`✅ File exists: ${filePath}`);
  console.log(`📏 Size: ${sizeKB} KB`);
  console.log(`📅 Last modified: ${lastModified.toLocaleString()}`);
  console.log(`⏰ Age: ${ageMinutes} minutes ago`);
  
  if (ageMinutes > 60) {
    console.log(`⚠️  File is ${ageMinutes} minutes old - you may need to rebuild`);
  } else {
    console.log(`✅ File is recent (less than 1 hour old)`);
  }
  
  return true;
}

function checkAllPossiblePaths() {
  console.log(`\n🔍 Checking all possible widget paths:`);
  
  let foundPath = null;
  
  for (const [pathType, paths] of Object.entries(POSSIBLE_PATHS)) {
    console.log(`\n📁 Testing ${pathType} paths:`);
    
    const jsExists = fs.existsSync(paths.js);
    const cssExists = fs.existsSync(paths.css);
    
    console.log(`   JS (${paths.js}): ${jsExists ? '✅' : '❌'}`);
    console.log(`   CSS (${paths.css}): ${cssExists ? '✅' : '❌'}`);
    
    if (jsExists && cssExists) {
      console.log(`✅ Found working path: ${pathType}`);
      foundPath = { type: pathType, ...paths };
    }
  }
  
  if (foundPath) {
    console.log(`\n🎯 RECOMMENDED PATH: ${foundPath.type}`);
    console.log(`   JS: ${foundPath.js}`);
    console.log(`   CSS: ${foundPath.css}`);
    
    // Check the found files
    checkFile(foundPath.js, `Widget JavaScript (${foundPath.type})`);
    checkFile(foundPath.css, `Widget CSS (${foundPath.type})`);
    
    return foundPath;
  } else {
    console.log(`\n❌ No working paths found!`);
    console.log(`\n🔧 BUILD THE WIDGET FIRST:`);
    console.log(`   cd ../..  # Go to widget root`);
    console.log(`   npm run build`);
    console.log(`   cd theming-app  # Back here`);
    return null;
  }
}

function checkBuildContents(jsPath) {
  console.log(`\n🔍 Checking build contents:`);
  
  try {
    const jsContent = fs.readFileSync(jsPath, 'utf8');
    
    // Check for common patterns
    const hasInit = jsContent.includes('initChatbotWidget');
    const hasReact = jsContent.includes('React');
    const hasWidget = jsContent.includes('ChatWidget') || jsContent.includes('chatbot');
    
    console.log(`🔧 Contains initChatbotWidget: ${hasInit ? '✅' : '❌'}`);
    console.log(`⚛️  Contains React code: ${hasReact ? '✅' : '❌'}`);
    console.log(`🤖 Contains widget code: ${hasWidget ? '✅' : '❌'}`);
    
    // Check if it's a UMD build
    const isUMD = jsContent.includes('(function (global, factory)') || jsContent.includes('typeof exports');
    console.log(`📦 UMD format: ${isUMD ? '✅' : '❌'}`);
    
    if (!hasInit) {
      console.log(`❌ Missing initChatbotWidget function - this build may be incomplete`);
    }
    
  } catch (error) {
    console.log(`❌ Error reading build file: ${error.message}`);
  }
}

function checkEnvironment() {
  console.log(`\n🔍 Checking environment:`);
  
  const envFile = '.env.local';
  if (fs.existsSync(envFile)) {
    console.log(`✅ Found .env.local file`);
    
    const content = fs.readFileSync(envFile, 'utf8');
    const lines = content.split('\n').filter(line => line.trim() && !line.startsWith('#'));
    
    lines.forEach(line => {
      if (line.includes('VITE_WIDGET_SOURCE')) {
        console.log(`📋 ${line}`);
      }
      if (line.includes('VITE_WIDGET_DEBUG')) {
        console.log(`📋 ${line}`);
      }
      if (line.includes('VITE_LOCAL_WIDGET')) {
        console.log(`📋 ${line}`);
      }
    });
  } else {
    console.log(`ℹ️  No .env.local file found - using defaults`);
  }
}

function generateEnvRecommendation(foundPath) {
  if (!foundPath) return;
  
  console.log(`\n📝 RECOMMENDED .env.local CONFIGURATION:`);
  console.log(`   # Copy this to your .env.local file`);
  console.log(`   VITE_WIDGET_SOURCE=local`);
  console.log(`   VITE_LOCAL_WIDGET_JS_PATH=${foundPath.js}`);
  console.log(`   VITE_LOCAL_WIDGET_CSS_PATH=${foundPath.css}`);
  console.log(`   VITE_WIDGET_DEBUG=true`);
}

function main() {
  console.log(`🔧 LOCAL BUILD CHECKER`);
  console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  
  const foundPath = checkAllPossiblePaths();
  
  if (foundPath) {
    checkBuildContents(foundPath.js);
  }
  
  checkEnvironment();
  
  if (foundPath) {
    generateEnvRecommendation(foundPath);
  }
  
  console.log(`\n💡 NEXT STEPS:`);
  
  if (!foundPath) {
    console.log(`1. 🔨 Build the widget: cd ../.. && npm run build`);
    console.log(`2. 🔄 Run this checker again: npm run widget:check`);
  } else {
    console.log(`1. ✅ Files exist - good!`);
    console.log(`2. 📝 Update .env.local with recommended paths above`);
  }
  
  console.log(`3. 🌐 Start theming app: npm run dev:local`);
  console.log(`4. 🕵️  Check browser console for loading messages`);
  console.log(`5. 🔄 Hard refresh browser (Ctrl+Shift+R / Cmd+Shift+R)`);
  console.log(`6. 🔍 Check Network tab in DevTools for 404 errors`);
  
  console.log(`\n🚀 Quick commands:`);
  console.log(`   npm run widget:status  - Show current config`);
  console.log(`   npm run dev:local      - Start with local build`);
  console.log(`   npm run dev:npm        - Start with NPM package`);
  
  console.log(`\n📋 PATH COMPARISON WITH DEMO.HTML:`);
  console.log(`   Demo.html uses: ./dist/chatbot-widget.umd.js`);
  console.log(`   Theming app needs: ./dist/ or ../dist/ (depends on structure)`);
  console.log(`   Current default: ./dist/ (changed to match demo.html)`);
}

main(); 