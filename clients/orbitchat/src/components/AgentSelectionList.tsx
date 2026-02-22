import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
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
  subtitle = '',
  eyebrow = ''
}: AgentSelectionListProps) {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [canScrollDown, setCanScrollDown] = useState(false);

  const checkScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) {
      setCanScrollDown(false);
      return;
    }
    setCanScrollDown(el.scrollHeight - el.scrollTop - el.clientHeight > 20);
  }, []);

  const focusFirstAgentCard = () => {
    const cardButtons = scrollContainerRef.current?.querySelectorAll<HTMLButtonElement>('button[data-agent-card="true"]');
    const firstCard = cardButtons?.[0] ?? null;
    if (!firstCard) {
      return;
    }
    firstCard.focus();
    firstCard.scrollIntoView({ block: 'nearest' });
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const canFocusCards = !isLoading && !error && filteredAdapters.length > 0;
    if (!canFocusCards) {
      return;
    }
    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault();
      focusFirstAgentCard();
    }
  };

  const filteredAdapters = useMemo(() => {
    const trimmedQuery = searchQuery.trim().toLowerCase();
    if (!trimmedQuery) {
      return adapters;
    }
    return adapters.filter(adapter => {
      const nameMatches = adapter.name.toLowerCase().includes(trimmedQuery);
      const descriptionMatches = adapter.description?.toLowerCase().includes(trimmedQuery) ?? false;
      const modelMatches = adapter.model?.toLowerCase().includes(trimmedQuery) ?? false;
      return nameMatches || descriptionMatches || modelMatches;
    });
  }, [adapters, searchQuery]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    checkScroll();
    el.addEventListener('scroll', checkScroll, { passive: true });
    return () => el.removeEventListener('scroll', checkScroll);
  }, [checkScroll, filteredAdapters]);

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

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="grid gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className={`${SKELETON_CARD_HEIGHT} animate-pulse rounded-2xl border border-gray-200 bg-transparent dark:border-[#3b3c49]`}
            />
          ))}
        </div>
      );
    }

    if (error) {
      return (
        <div className="rounded-2xl border border-red-200 bg-transparent px-4 py-6 text-sm text-red-700 dark:border-red-900 dark:text-red-200">
          {error}
        </div>
      );
    }

    if (adapters.length === 0) {
      return (
        <div className="rounded-2xl border border-gray-200 bg-transparent px-4 py-6 text-sm text-gray-600 dark:border-[#3b3c49] dark:text-gray-300">
          No agents are available yet. Configure adapters in your middleware settings to continue.
        </div>
      );
    }

    if (filteredAdapters.length === 0) {
      return (
        <div className="rounded-2xl border border-gray-200 bg-transparent px-4 py-6 text-sm text-gray-600 dark:border-[#3b3c49] dark:text-gray-300">
          No agents match your search.
        </div>
      );
    }

    return (
      <div className="relative flex flex-col h-full min-h-0">
        <div
          ref={scrollContainerRef}
          className="flex-1 min-h-0 overflow-y-auto pr-1 pb-2"
        >
          <div className="grid gap-3 lg:grid-cols-2">
            {filteredAdapters.map(adapter => (
              <AgentCard key={adapter.name} adapter={adapter} onSelect={selected => onAdapterSelect(selected.name)} />
            ))}
          </div>
        </div>
        {canScrollDown && (
          <div
            className="pointer-events-none absolute bottom-0 left-0 right-0 h-12 md:hidden bg-gradient-to-t from-white dark:from-[#212121] to-transparent"
            aria-hidden="true"
          />
        )}
      </div>
    );
  };

  return (
    <div className={`flex w-full flex-col gap-4 md:gap-6 ${className}`}>
      {(eyebrow || title || subtitle) && (
        <div className="flex-shrink-0">
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
      <div className="relative w-full flex-shrink-0">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search agents"
          value={searchQuery}
          disabled={isLoading || !!error || adapters.length === 0}
          onChange={event => setSearchQuery(event.target.value)}
          onKeyDown={handleSearchKeyDown}
          className="w-full rounded-md border border-gray-300 bg-transparent py-2 pl-9 pr-3 text-sm text-gray-900 placeholder-gray-400 shadow-inner focus:border-gray-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#3b3c49] dark:text-white dark:shadow-none"
        />
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {renderContent()}
      </div>
    </div>
  );
}
