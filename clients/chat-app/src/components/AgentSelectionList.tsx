import { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
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
  title = '',
  subtitle = 'Each agent is tuned for a specific expertise. Pick one to start a focused conversation.',
  eyebrow = 'Pick an Agent'
}: AgentSelectionListProps) {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [showScrollHint, setShowScrollHint] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAdapters = useMemo(() => {
    const trimmedQuery = searchQuery.trim().toLowerCase();
    if (!trimmedQuery) {
      return adapters;
    }
    return adapters.filter(adapter => {
      const nameMatches = adapter.name.toLowerCase().includes(trimmedQuery);
      const descriptionMatches = adapter.description?.toLowerCase().includes(trimmedQuery) ?? false;
      return nameMatches || descriptionMatches;
    });
  }, [adapters, searchQuery]);

  useEffect(() => {
    let mounted = true;

    const loadAdapters = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const adapterList = await fetchAdapters();
        const sortedAdapters = adapterList.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
        if (mounted) {
          setAdapters(sortedAdapters);
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
  }, [filteredAdapters, isLoading, error]);

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

    if (filteredAdapters.length === 0) {
      return (
        <div className="rounded-2xl border border-gray-200 bg-white px-4 py-6 text-sm text-gray-600 dark:border-[#3b3c49] dark:bg-[#22232b] dark:text-gray-300">
          No agents match your search.
        </div>
      );
    }

    return (
      <div className="relative">
        <div
          ref={scrollContainerRef}
          className="max-h-[75vh] lg:max-h-[70vh] overflow-y-auto pr-1 pt-3 pb-1"
          onScroll={() => {
            const el = scrollContainerRef.current;
            if (!el) return;
            const shouldShow = el.scrollHeight - el.scrollTop - el.clientHeight > 4;
            setShowScrollHint(shouldShow);
          }}
        >
          <div className="grid gap-3">
            {filteredAdapters.map(adapter => (
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
      <div className="relative w-full">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search agents"
          value={searchQuery}
          disabled={isLoading || !!error || adapters.length === 0}
          onChange={event => setSearchQuery(event.target.value)}
          className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 placeholder-gray-400 shadow-inner focus:border-gray-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#3b3c49] dark:bg-[#1f2027] dark:text-white dark:shadow-none"
        />
      </div>
      {renderContent()}
    </div>
  );
}
