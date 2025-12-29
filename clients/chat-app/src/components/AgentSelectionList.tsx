import { useEffect, useRef, useState } from 'react';
import { AgentCard } from './AgentCard';
import { fetchAdapters, type Adapter } from '../utils/middlewareConfig';
import { debugError } from '../utils/debug';

interface AgentSelectionListProps {
  onAdapterSelect: (adapterName: string) => void;
  className?: string;
  title?: string;
  subtitle?: string;
  eyebrow?: string;
}

const SKELETON_CARD_HEIGHT = 'h-[96px]';

export function AgentSelectionList({
  onAdapterSelect,
  className = '',
  title = 'Choose an agent to get started',
  subtitle = 'Each agent is tuned for a specific expertise. Pick one to start a focused conversation.',
  eyebrow = 'Meet the specialists'
}: AgentSelectionListProps) {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [showScrollHint, setShowScrollHint] = useState(false);

  useEffect(() => {
    let mounted = true;

    const loadAdapters = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const adapterList = await fetchAdapters();
        if (mounted) {
          setAdapters(adapterList);
        }
      } catch (err) {
        debugError('[AgentSelectionList] Failed to load adapters', err);
        if (mounted) {
          setError('Unable to load agents right now.');
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    loadAdapters();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const updateScrollHint = () => {
      const el = scrollContainerRef.current;
      if (!el) {
        setShowScrollHint(false);
        return;
      }
      const shouldShow = el.scrollHeight - el.clientHeight > 4;
      setShowScrollHint(shouldShow);
    };

    updateScrollHint();
    window.addEventListener('resize', updateScrollHint);

    return () => {
      window.removeEventListener('resize', updateScrollHint);
    };
  }, [adapters, isLoading, error]);

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="grid gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className={`${SKELETON_CARD_HEIGHT} animate-pulse rounded-2xl border border-gray-200 bg-white dark:border-[#3b3c49] dark:bg-[#22232b]`}
            />
          ))}
        </div>
      );
    }

    if (error) {
      return (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-6 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      );
    }

    if (adapters.length === 0) {
      return (
        <div className="rounded-2xl border border-gray-200 bg-white px-4 py-6 text-sm text-gray-600 dark:border-[#3b3c49] dark:bg-[#22232b] dark:text-gray-300">
          No agents are available yet. Configure adapters in your middleware settings to continue.
        </div>
      );
    }

    return (
      <div className="relative">
        <div
          ref={scrollContainerRef}
          className="max-h-[75vh] lg:max-h-[70vh] overflow-y-auto pr-1"
          onScroll={() => {
            const el = scrollContainerRef.current;
            if (!el) return;
            const shouldShow = el.scrollHeight - el.scrollTop - el.clientHeight > 4;
            setShowScrollHint(shouldShow);
          }}
        >
          <div className="grid gap-3">
            {adapters.map(adapter => (
              <AgentCard key={adapter.name} adapter={adapter} onSelect={selected => onAdapterSelect(selected.name)} />
            ))}
          </div>
        </div>
        {showScrollHint && (
          <>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-b from-transparent to-white dark:to-[#1c1d23]" />
            <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-gray-600 shadow-sm dark:bg-[#1c1d23]/95 dark:text-gray-200">
              Scroll for more
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className={`flex w-full flex-col gap-6 ${className}`}>
      {(eyebrow || title || subtitle) && (
        <div>
          {eyebrow && (
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-300">
              {eyebrow}
            </p>
          )}
          {title && (
            <h2 className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
              {title}
            </h2>
          )}
          {subtitle && (
            <p className="mt-2 text-base text-gray-600 dark:text-gray-300">
              {subtitle}
            </p>
          )}
        </div>
      )}
      {renderContent()}
    </div>
  );
}
