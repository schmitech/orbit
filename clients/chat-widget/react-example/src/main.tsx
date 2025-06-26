import React from 'react'
import { createRoot, Container } from 'react-dom/client'
import App from './App'
import './index.css'

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Failed to find the root element');
// @ts-ignore
createRoot(rootElement as HTMLElement).render(<App />) 