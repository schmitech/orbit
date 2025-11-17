#!/usr/bin/env node

// Main entry point for ORBIT CLI
// This file loads the compiled TypeScript code from orbit-cli

const path = require('path');
const fs = require('fs');

// Determine if we should use compiled code or ts-node for development
const isDevelopment = process.env.NODE_ENV === 'development' || process.env.ORBIT_DEV === '1';

const orbitCliPath = path.join(__dirname, 'orbit-cli');
const distPath = path.join(orbitCliPath, 'dist', 'index.js');
const srcPath = path.join(orbitCliPath, 'src', 'index.ts');

if (isDevelopment) {
  // Development mode: use ts-node
  try {
    const tsNodePath = require.resolve('ts-node/register', { paths: [orbitCliPath] });
    require(tsNodePath);
    require(srcPath);
  } catch (error) {
    console.error('Failed to load ts-node. Make sure dependencies are installed:');
    console.error('  cd bin/orbit-cli && npm install');
    process.exit(1);
  }
} else {
  // Production mode: use compiled JavaScript
  if (fs.existsSync(distPath)) {
    require(distPath);
  } else {
    // If dist doesn't exist, try to build it or use ts-node as fallback
    console.error('Compiled code not found. Attempting to build...');
    try {
      const { execSync } = require('child_process');
      execSync('npm run build', { 
        cwd: orbitCliPath,
        stdio: 'inherit'
      });
      if (fs.existsSync(distPath)) {
        require(distPath);
      } else {
        throw new Error('Build completed but dist/index.js not found');
      }
    } catch (buildError) {
      console.error('Build failed. Trying ts-node as fallback...');
      try {
        const tsNodePath = require.resolve('ts-node/register', { paths: [orbitCliPath] });
        require(tsNodePath);
        require(srcPath);
      } catch (tsNodeError) {
        console.error('Failed to use ts-node fallback. Please build the project:');
        console.error('  cd bin/orbit-cli && npm install && npm run build');
        process.exit(1);
      }
    }
  }
}

