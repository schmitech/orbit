#!/usr/bin/env node

import fs from 'fs';
import path from 'path';

const WIDGET_DIST = '../dist';
const PUBLIC_DIST = 'public/dist';

function copyFile(src, dest) {
  try {
    // Ensure destination directory exists
    const destDir = path.dirname(dest);
    if (!fs.existsSync(destDir)) {
      fs.mkdirSync(destDir, { recursive: true });
    }
    
    // Copy file
    fs.copyFileSync(src, dest);
    
    const stats = fs.statSync(dest);
    const sizeKB = Math.round(stats.size / 1024);
    console.log(`✅ Copied ${src} → ${dest} (${sizeKB} KB)`);
    return true;
  } catch (error) {
    console.error(`❌ Failed to copy ${src} → ${dest}:`, error.message);
    return false;
  }
}

function main() {
  console.log('📦 Copying widget files to public directory for Vite serving...\n');
  
  const files = [
    {
      src: path.join(WIDGET_DIST, 'chatbot-widget.umd.js'),
      dest: path.join(PUBLIC_DIST, 'chatbot-widget.umd.js')
    },
    {
      src: path.join(WIDGET_DIST, 'chatbot-widget.css'),
      dest: path.join(PUBLIC_DIST, 'chatbot-widget.css')
    }
  ];
  
  let allSuccess = true;
  
  for (const file of files) {
    if (!fs.existsSync(file.src)) {
      console.error(`❌ Source file not found: ${file.src}`);
      console.log(`💡 Run: cd ../.. && npm run build`);
      allSuccess = false;
      continue;
    }
    
    const success = copyFile(file.src, file.dest);
    if (!success) allSuccess = false;
  }
  
  if (allSuccess) {
    console.log('\n🎉 All widget files copied successfully!');
    console.log('\n📋 Updated paths for Vite:');
    console.log('   JS:  /dist/chatbot-widget.umd.js');
    console.log('   CSS: /dist/chatbot-widget.css');
    console.log('\n💡 These paths are now accessible via Vite dev server');
  } else {
    console.log('\n❌ Some files failed to copy');
    process.exit(1);
  }
}

main(); 