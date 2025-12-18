#!/usr/bin/env node

import fs from 'fs';
import path from 'path';

const ENV_FILE = '.env.local';
const args = process.argv.slice(2);
const command = args[0];

function readEnvFile() {
  if (!fs.existsSync(ENV_FILE)) {
    return {};
  }
  
  const content = fs.readFileSync(ENV_FILE, 'utf8');
  const env = {};
  
  content.split('\n').forEach(line => {
    const [key, ...valueParts] = line.split('=');
    if (key && valueParts.length > 0) {
      env[key.trim()] = valueParts.join('=').trim();
    }
  });
  
  return env;
}

function writeEnvFile(env) {
  const content = Object.entries(env)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
  
  fs.writeFileSync(ENV_FILE, content + '\n');
}

function showStatus() {
  const env = readEnvFile();
  const source = env.VITE_WIDGET_SOURCE || 'npm';
  
  console.log(`\n🎛️  Current widget source: ${source.toUpperCase()}`);
  
  if (source === 'local') {
    console.log(`   📁 JS Path: ${env.VITE_LOCAL_WIDGET_JS_PATH || '../dist/chatbot-widget.umd.js'}`);
    console.log(`   📁 CSS Path: ${env.VITE_LOCAL_WIDGET_CSS_PATH || '../dist/chatbot-widget.css'}`);
  } else {
    console.log(`   📦 NPM Version: ${env.VITE_NPM_WIDGET_VERSION || '0.4.9'}`);
  }
  
  console.log('\n💡 Commands:');
  console.log('   npm run dev:local  - Use local build');
  console.log('   npm run dev:npm    - Use NPM package');
  console.log('   node scripts/toggle-widget-source.js local   - Set to local');
  console.log('   node scripts/toggle-widget-source.js npm     - Set to NPM');
  console.log('   node scripts/toggle-widget-source.js status  - Show current status\n');
}

function setSource(source) {
  if (!['local', 'npm'].includes(source)) {
    console.error('❌ Invalid source. Use "local" or "npm"');
    process.exit(1);
  }
  
  const env = readEnvFile();
  env.VITE_WIDGET_SOURCE = source;
  
  // Set defaults if not present
  if (!env.VITE_LOCAL_WIDGET_JS_PATH) {
    env.VITE_LOCAL_WIDGET_JS_PATH = '../dist/chatbot-widget.umd.js';
  }
  if (!env.VITE_LOCAL_WIDGET_CSS_PATH) {
    env.VITE_LOCAL_WIDGET_CSS_PATH = '../dist/chatbot-widget.css';
  }
  if (!env.VITE_NPM_WIDGET_VERSION) {
    env.VITE_NPM_WIDGET_VERSION = '0.4.9';
  }
  
  writeEnvFile(env);
  
  console.log(`✅ Widget source set to: ${source.toUpperCase()}`);
  
  if (source === 'local') {
    console.log('💡 Make sure to build the widget first: npm run build (from widget directory)');
  }
  
  console.log(`🚀 Start development: npm run dev:${source}`);
}

// Main logic
switch (command) {
  case 'local':
  case 'npm':
    setSource(command);
    break;
  case 'status':
  case undefined:
    showStatus();
    break;
  default:
    console.error(`❌ Unknown command: ${command}`);
    console.log('Usage: node toggle-widget-source.js [local|npm|status]');
    process.exit(1);
} 