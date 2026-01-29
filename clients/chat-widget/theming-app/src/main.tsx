import React, { StrictMode } from 'react'
import * as ReactDOM from 'react-dom'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
