import { ChevronRight } from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter) => void;
}

const EMOJI_REGEX = /\p{Extended_Pictographic}/u;

const getAvatarSymbol = (name: string): string => {
  const emojiMatch = name.match(EMOJI_REGEX);
  if (emojiMatch) {
    return emojiMatch[0];
  }

  const trimmedName = name.trim();
  if (trimmedName.length === 0) {
    return '?';
  }

  return trimmedName[0]?.toUpperCase() ?? '?';
};

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const avatarSymbol = getAvatarSymbol(adapter.name);

  return (
    <button
      type="button"
      onClick={() => onSelect(adapter)}
      className="group flex w-full items-center gap-4 rounded-2xl border border-gray-200 bg-white px-4 py-4 text-left transition-all duration-200 md:hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:border-[#3b3c49] dark:bg-[#22232b] dark:hover:border-blue-400/50 dark:focus-visible:ring-blue-400"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-100 text-2xl dark:bg-[#2f303d]">
        {avatarSymbol}
      </div>
      <div className="min-w-0 flex-1 flex flex-col gap-1">
        <span className="truncate text-base font-semibold text-gray-900 dark:text-white">
          {adapter.name}
        </span>
        {adapter.description && (
          <span className="line-clamp-2 text-sm text-gray-600 dark:text-gray-300">
            {adapter.description}
          </span>
        )}
      </div>
      <div className="ml-auto flex h-10 w-10 items-center justify-center rounded-full border border-transparent bg-gray-50 text-gray-400 transition-colors group-hover:border-blue-100 group-hover:bg-white group-hover:text-blue-500 dark:bg-[#2a2b34] dark:text-gray-400 dark:group-hover:border-blue-500/40 dark:group-hover:bg-transparent dark:group-hover:text-blue-300">
        <ChevronRight className="h-5 w-5" />
      </div>
    </button>
  );
}
