import { useState, useEffect, useRef, useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import { fetchAdapters, type Adapter } from '../utils/middlewareConfig';
import { debugError } from '../utils/debug';

interface AdapterSelectorProps {
  selectedAdapter: string | null;
  onAdapterChange: (adapterName: string) => void;
  disabled?: boolean;
  defaultAdapterName?: string | null;
  showDescriptions?: boolean;
  variant?: 'sidebar' | 'prominent';
  label?: string;
  showLabel?: boolean;
}

export function AdapterSelector({
  selectedAdapter,
  onAdapterChange,
  disabled,
  defaultAdapterName,
  showDescriptions = false,
  variant = 'sidebar',
  label,
  showLabel
}: AdapterSelectorProps) {
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

  const onAdapterChangeRef = useRef(onAdapterChange);
  const hasAutoSelectedDefault = useRef(false);

  useEffect(() => {
    onAdapterChangeRef.current = onAdapterChange;
  }, [onAdapterChange]);

  useEffect(() => {
    if (selectedAdapter) {
      hasAutoSelectedDefault.current = true;
      return;
    }

    if (!defaultAdapterName || hasAutoSelectedDefault.current || adapters.length === 0) {
      return;
    }

    const hasMatchingAdapter = adapters.some(adapter => adapter.name === defaultAdapterName);
    if (!hasMatchingAdapter) {
      return;
    }

    hasAutoSelectedDefault.current = true;
    onAdapterChangeRef.current(defaultAdapterName);
  }, [adapters, selectedAdapter, defaultAdapterName]);

  const selectedAdapterObj = adapters.find(a => a.name === selectedAdapter);

  const computedShowLabel = typeof showLabel === 'boolean' ? showLabel : variant === 'prominent';
  const labelText = label || (variant === 'prominent' ? 'Select an agent' : 'Adapter');

  const containerClasses = useMemo(() => {
    if (variant === 'prominent') {
      return 'relative w-full text-left';
    }
    return 'relative w-full';
  }, [variant]);

  const buttonClasses = useMemo(() => {
    const base = 'w-full rounded-md border bg-white px-4 py-3 text-left text-sm text-[#353740] focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 dark:bg-[#343541] dark:text-[#ececf1]';
    if (variant === 'prominent') {
      return [
        base,
        'border-gray-300 shadow-sm transition-all duration-200 focus-visible:ring-blue-500 dark:border-[#4a4b54] dark:focus-visible:ring-blue-400'
      ].join(' ');
    }
    return [
      'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-left text-sm text-[#353740] focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1] dark:focus:border-[#6b6f7a]'
    ].join(' ');
  }, [variant]);

  const dropdownClasses = useMemo(() => {
    if (variant === 'prominent') {
      return 'absolute z-20 mt-2 w-full rounded-xl border border-gray-200 bg-white shadow-xl ring-1 ring-black/5 dark:border-[#4a4b54] dark:bg-[#1f2027]';
    }
    return 'absolute z-20 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg ring-1 ring-black/5 dark:border-[#4a4b54] dark:bg-[#1f2027]';
  }, [variant]);

  const visibleLabelClass =
    'mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-[#bfc2cd]';
  const prominentLabelClass = '!text-sm !font-semibold !text-gray-700 dark:!text-white';
  const labelClasses = computedShowLabel
    ? `${visibleLabelClass} ${variant === 'prominent' ? prominentLabelClass : ''}`
    : 'sr-only';

  return (
    <div className={containerClasses}>
      <label className={labelClasses}>
        {labelText}
      </label>
      <div className="relative">
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled || isLoading || adapters.length === 0}
          className={`${buttonClasses} disabled:opacity-50 disabled:cursor-not-allowed`}
          aria-label={labelText}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-col min-w-0">
              <span className={`truncate font-medium ${selectedAdapterObj ? 'text-[#11121a] dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
                {isLoading ? 'Loading agents…' : 
                 error ? 'Error loading agents' :
                 selectedAdapterObj ? selectedAdapterObj.name :
                 adapters.length === 0 ? 'No agents available' :
                 'Select an agent'}
              </span>
              {variant === 'prominent' && selectedAdapterObj?.description && (
                <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {selectedAdapterObj.description}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 flex-shrink-0 transition-transform text-gray-400 dark:text-gray-300 ${isOpen ? 'rotate-180' : ''}`} />
          </div>
        </button>

        {isOpen && !disabled && adapters.length > 0 && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setIsOpen(false)}
            />
            <div className={dropdownClasses}>
              <div className="max-h-72 overflow-auto py-2">
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
                      className={`w-full px-4 py-3 text-left text-sm transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
                          : 'text-[#353740] hover:bg-gray-50 dark:text-[#ececf1] dark:hover:bg-[#2a2d35]'
                      }`}
                    >
                      <div className="flex flex-col gap-1">
                        <span className="font-medium truncate">{adapter.name}</span>
                        {showDescriptions && adapter.description && (
                          <span
                            className="text-xs text-gray-500 dark:text-gray-400"
                            style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                          >
                            {adapter.description}
                          </span>
                        )}
                      </div>
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
