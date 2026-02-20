import { useState, useEffect, useRef, useCallback } from 'react';
import { ApiClient } from '@schmitech/chatbot-api';
import { saveConnection, getStoredConnection } from '../config/connection';
import type { ConnectionConfig } from '../config/connection';
import { resetApiClient } from '../api/client';

interface ConnectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: (config: ConnectionConfig) => void;
}

const DEFAULT_URL = 'http://localhost:3000';

export function ConnectionDialog({ isOpen, onClose, onSaved }: ConnectionDialogProps) {
  const [apiUrl, setApiUrl] = useState(DEFAULT_URL);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      const stored = getStoredConnection();
      if (stored) {
        setApiUrl(stored.apiUrl);
        setApiKey(stored.apiKey);
      } else {
        setApiUrl(DEFAULT_URL);
        setApiKey('');
      }
      setError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const timeoutId = requestAnimationFrame(() => {
      firstInputRef.current?.focus();
    });
    return () => cancelAnimationFrame(timeoutId);
  }, [isOpen]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (!testing) onClose();
      }
    },
    [testing, onClose]
  );


  const handleSave = async () => {
    const url = apiUrl.trim();
    if (!url) {
      setError('Orbit URL is required');
      return;
    }
    setError(null);
    setTesting(true);
    try {
      const client = new ApiClient({
        apiUrl: url,
        apiKey: apiKey.trim() || undefined,
      });
      await client.getAdapterInfo();
      const config: ConnectionConfig = { apiUrl: url, apiKey: apiKey.trim() };
      saveConnection(config);
      resetApiClient();
      onSaved(config);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed');
    } finally {
      setTesting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="connection-overlay" role="presentation">
      <div
        ref={dialogRef}
        className="connection-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="connection-title"
        aria-describedby="connection-hint"
        onKeyDown={handleKeyDown}
      >
        <h2 id="connection-title">Connect to Orbit</h2>
        <p id="connection-hint" className="connection-hint">
          Enter your Orbit server URL and API key. They are stored only in this browser.
        </p>
        <label htmlFor="connection-api-url">
          Orbit URL
        </label>
        <input
          id="connection-api-url"
          ref={firstInputRef}
          type="url"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
          placeholder="https://your-orbit-server.com"
          disabled={testing}
          autoComplete="url"
          aria-required="true"
          aria-invalid={!!error}
        />
        <label htmlFor="connection-api-key">
          API key
        </label>
        <div className="connection-input-with-icon">
          <input
            id="connection-api-key"
            type={showApiKey ? 'text' : 'password'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Your API key"
            disabled={testing}
            autoComplete="off"
          />
          <button
            type="button"
            id="api-key-toggle"
            className="connection-toggle-password"
            onClick={() => setShowApiKey((v) => !v)}
            disabled={testing}
            title={showApiKey ? 'Hide API key' : 'Show API key'}
            aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
            aria-pressed={showApiKey}
          >
              {showApiKey ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
        </div>
        {error && (
          <p className="connection-error" role="alert" id="connection-error">
            {error}
          </p>
        )}
        <div className="connection-actions">
          <button type="button" onClick={onClose} disabled={testing}>
            Cancel
          </button>
          <button type="button" onClick={handleSave} disabled={testing}>
            {testing ? 'Testing…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
