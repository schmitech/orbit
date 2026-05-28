import { ChevronRight } from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter) => void;
}

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const description = adapter.description?.trim();
  const { isDark } = useTheme();
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';

  const handleCardActivate = () => onSelect(adapter);

  return (
    <div
      tabIndex={0}
      role="button"
      data-agent-card="true"
      onClick={handleCardActivate}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleCardActivate();
        }
      }}
      className="group relative flex w-full cursor-pointer flex-col rounded-2xl border border-slate-200 bg-white px-4 py-3.5 text-left shadow-sm transition-colors duration-150 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/30 dark:border-[#242424] dark:bg-[#080808] dark:hover:border-[#333333] dark:hover:bg-[#111111] dark:focus-visible:ring-sky-400/30 md:px-5 md:py-4"
    >
      <div className="relative">
        <div className="min-w-0">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-semibold text-sky-900 dark:text-sky-300 md:text-base">
                {adapter.name}
              </p>

              {description ? (
                <div className="mt-1 text-sm leading-5 text-slate-600 dark:text-slate-300">
                  <MarkdownRenderer
                    content={description}
                    className="prose prose-slate max-w-none text-inherit dark:prose-invert [&>*]:mb-0 [&>*]:mt-0 [&_p]:overflow-hidden [&_p]:text-ellipsis [&_p]:[display:-webkit-box] [&_p]:[-webkit-box-orient:vertical] [&_p]:[-webkit-line-clamp:4]"
                    syntaxTheme={syntaxTheme}
                  />
                </div>
              ) : (
                <p className="mt-1 text-sm leading-5 text-slate-500 dark:text-slate-400">
                  Configure this agent to see its capabilities.
                </p>
              )}
            </div>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleCardActivate();
              }}
              className="hidden h-8 w-8 flex-shrink-0 items-center justify-center self-start rounded-full text-slate-700 transition-all duration-150 hover:bg-slate-100 group-hover:translate-x-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/30 dark:text-slate-200 dark:hover:bg-white/10 dark:focus-visible:ring-sky-400/30 md:inline-flex"
              aria-label={`Start conversation with ${adapter.name}`}
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-end gap-3 border-t border-slate-200 pt-2.5 text-xs text-slate-500 dark:border-white/10 dark:text-slate-400 md:hidden">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            handleCardActivate();
          }}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-700 transition-all duration-150 hover:bg-slate-100 group-hover:translate-x-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/30 dark:text-slate-200 dark:hover:bg-white/10 dark:focus-visible:ring-sky-400/30"
          aria-label={`Start conversation with ${adapter.name}`}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
