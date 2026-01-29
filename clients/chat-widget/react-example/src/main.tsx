import React from 'react'
import * as ReactDOM from 'react-dom'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// Expose React and ReactDOM as globals for UMD widget compatibility
// React 19 removed UMD builds, so we expose the ESM imports as globals
declare global {
  interface Window {
    React: typeof React;
    ReactDOM: typeof ReactDOM;
  }
}
window.React = React;
window.ReactDOM = ReactDOM;

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Failed to find the root element');
createRoot(rootElement as HTMLElement).render(<App />) 