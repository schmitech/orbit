import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Search, X } from 'lucide-react';
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
              <AgentCard key={adapter.id} adapter={adapter} onSelect={selected => onAdapterSelect(selected.id)} />
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
      <div className="flex w-full flex-shrink-0 justify-center">
        <div className="w-full max-w-xl lg:max-w-2xl">
        <div className="relative overflow-hidden rounded-[1.75rem] border border-slate-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.94))] shadow-[0_10px_28px_rgba(15,23,42,0.05)] transition-all duration-200 focus-within:border-sky-300/90 focus-within:shadow-[0_0_0_1px_rgba(125,211,252,0.55),0_10px_28px_rgba(15,23,42,0.05)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(37,39,49,0.95),rgba(29,31,39,0.92))] dark:shadow-[0_12px_30px_rgba(0,0,0,0.2)] dark:focus-within:border-sky-400/30 dark:focus-within:shadow-[0_0_0_1px_rgba(56,189,248,0.22),0_12px_30px_rgba(0,0,0,0.2)]">
          <div className="pointer-events-none absolute inset-0 rounded-[inherit] bg-[linear-gradient(180deg,rgba(255,255,255,0.45),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0))]" />
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
          <input
            type="text"
            placeholder="Search agents"
            value={searchQuery}
            maxLength={100}
            disabled={isLoading || !!error || adapters.length === 0}
            onChange={event => setSearchQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="relative z-10 w-full bg-transparent py-3 pl-11 pr-11 text-sm font-medium text-slate-700 placeholder:font-normal placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-100 dark:placeholder:text-slate-500"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 z-10 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200/80 bg-white/90 text-slate-400 transition-colors hover:border-slate-300 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-200 dark:border-white/10 dark:bg-white/5 dark:text-slate-500 dark:hover:border-white/20 dark:hover:text-slate-200 dark:focus:ring-sky-500/20"
              aria-label="Clear search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {renderContent()}
      </div>
    </div>
  );
}
