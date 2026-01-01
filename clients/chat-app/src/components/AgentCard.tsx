import { ChevronRight } from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter) => void;
}

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const description = adapter.description?.trim();
  return (
    <button
      type="button"
      onClick={() => onSelect(adapter)}
      className="group flex w-full flex-col gap-3 rounded-2xl border border-gray-200 bg-white p-4 text-left transition-all duration-200 hover:border-blue-200 hover:shadow-[0_15px_45px_rgba(15,23,42,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:border-[#3b3c49] dark:bg-[#22232b] dark:hover:border-blue-400/50 dark:focus-visible:ring-blue-400"
    >
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-semibold text-gray-900 dark:text-white">
            {adapter.name}
          </p>
        </div>
        <div className="ml-auto flex h-10 w-10 items-center justify-center rounded-full border border-transparent bg-gray-50 text-gray-400 transition-colors group-hover:border-blue-100 group-hover:bg-white group-hover:text-blue-500 dark:bg-[#2a2b34] dark:text-gray-400 dark:group-hover:border-blue-500/40 dark:group-hover:bg-transparent dark:group-hover:text-blue-300">
          <ChevronRight className="h-5 w-5" />
        </div>
      </div>
      {description ? (
        <p className="line-clamp-3 text-sm leading-relaxed text-gray-600 dark:text-gray-200">
          {description}
        </p>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Configure this agent to see its capabilities.
        </p>
      )}
    </button>
  );
}
