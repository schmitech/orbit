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
  const model = adapter.model?.trim();
  const { isDark } = useTheme();
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';

  return (
    <button
      type="button"
      data-agent-card="true"
      onClick={() => onSelect(adapter)}
      className="group relative flex w-full flex-col rounded-2xl border border-slate-200 bg-white px-4 py-3.5 text-left shadow-sm transition-colors duration-150 hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/30 dark:border-[#3b3c49] dark:bg-[#22252d] dark:hover:border-[#4b4f5c] dark:hover:bg-[#282b34] dark:focus-visible:ring-sky-400/30 md:px-5 md:py-4"
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

            <div className="hidden min-w-[132px] flex-shrink-0 flex-col items-end gap-3 self-stretch md:flex">
              {model ? (
                <span
                  className="max-w-full truncate text-xs font-medium text-sky-800 dark:text-sky-300"
                  title={model}
                  aria-label={`Model: ${model}`}
                >
                  {model}
                </span>
              ) : (
                <span />
              )}

              <span className="mt-auto inline-flex items-center text-slate-700 transition-transform duration-150 group-hover:translate-x-0.5 dark:text-slate-200">
                <ChevronRight className="h-4 w-4" />
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-slate-200 pt-2.5 text-xs text-slate-500 dark:border-white/10 dark:text-slate-400 md:hidden">
        {model ? (
          <span
            className="inline-flex max-w-full truncate text-xs font-medium text-sky-800 dark:text-sky-300"
            title={model}
            aria-label={`Model: ${model}`}
          >
            {model}
          </span>
        ) : (
          <span>Select agent</span>
        )}

        <span className="inline-flex items-center text-slate-700 transition-transform duration-150 group-hover:translate-x-0.5 dark:text-slate-200">
          <ChevronRight className="h-4 w-4" />
        </span>
      </div>
    </button>
  );
}
