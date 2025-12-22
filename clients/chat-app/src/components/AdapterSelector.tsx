import { useState, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { fetchAdapters, type Adapter } from '../utils/middlewareConfig';
import { debugError } from '../utils/debug';

interface AdapterSelectorProps {
  selectedAdapter: string | null;
  onAdapterChange: (adapterName: string) => void;
  disabled?: boolean;
}

export function AdapterSelector({ selectedAdapter, onAdapterChange, disabled }: AdapterSelectorProps) {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function loadAdapters() {
      try {
        setIsLoading(true);
        setError(null);
        const adapterList = await fetchAdapters();
        if (mounted) {
          setAdapters(adapterList);
        }
      } catch (err) {
        debugError('Failed to load adapters:', err);
        if (mounted) {
          setError('Failed to load adapters. Please check your connection.');
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadAdapters();

    return () => {
      mounted = false;
    };
  }, []);

  const hasInitialized = useRef(false);
  const onAdapterChangeRef = useRef(onAdapterChange);

  useEffect(() => {
    onAdapterChangeRef.current = onAdapterChange;
  }, [onAdapterChange]);

  useEffect(() => {
    if (selectedAdapter) {
      hasInitialized.current = true;
      return;
    }

    if (!hasInitialized.current && adapters.length > 0) {
      hasInitialized.current = true;
      // Wait for user interaction before selecting
    }
  }, [adapters, selectedAdapter]);

  const selectedAdapterObj = adapters.find(a => a.name === selectedAdapter);

  return (
    <div className="relative w-full">
      <label className="sr-only">Adapter</label>
      <div className="relative">
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled || isLoading || adapters.length === 0}
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-left text-sm text-[#353740] focus:border-gray-400 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1] dark:focus:border-[#6b6f7a]"
        >
          <div className="flex items-center justify-between gap-2">
            <span className={`truncate ${selectedAdapterObj ? '' : 'text-gray-500 dark:text-gray-400'}`}>
              {isLoading ? 'Loading adapters…' : 
               error ? 'Error loading adapters' :
               selectedAdapterObj ? selectedAdapterObj.name :
               adapters.length === 0 ? 'No adapters available' :
               'Select agent'}
            </span>
            <ChevronDown className={`h-4 w-4 flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </div>
        </button>

        {isOpen && !disabled && adapters.length > 0 && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setIsOpen(false)}
            />
            <div className="absolute z-20 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg ring-1 ring-black/5 dark:border-[#4a4b54] dark:bg-[#1f2027]">
              <div className="max-h-60 overflow-auto py-1">
                {adapters.map((adapter) => {
                  const isActive = adapter.name === selectedAdapter;
                  return (
                    <button
                      key={adapter.name}
                      type="button"
                      onClick={() => {
                        if (!isActive) {
                          onAdapterChange(adapter.name);
                        }
                        setIsOpen(false);
                      }}
                      className={`w-full px-3 py-2 text-left text-sm transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
                          : 'text-[#353740] hover:bg-gray-50 dark:text-[#ececf1] dark:hover:bg-[#2a2d35]'
                      }`}
                    >
                      <span className="font-medium truncate">{adapter.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
      {error && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  );
}
