import React, { StrictMode } from 'react'
import * as ReactDOM from 'react-dom'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Expose React and ReactDOM as globals for UMD widget compatibility.
// - NPM widget (0.7.1+): built with React 19 externals → use app's React 19.
// - Local widget: use React 18 from index.html (UMD expects React 18 internals).
// Window.React/ReactDOM are declared in src/types/widget.types.ts
const widgetSource = import.meta.env.VITE_WIDGET_SOURCE as string | undefined;
if (widgetSource === 'npm') {
  window.React = React;
  window.ReactDOM = ReactDOM;
}
// else: keep React 18 from index.html for local widget (don't overwrite)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
