import { 
  ChevronRight, 
  Bot, 
  Globe,
  Code,
  Image as ImageIcon,
  Video,
  FileText,
  Mic,
  Users,
  BarChart,
  ShoppingCart,
  Database,
  Search,
  Server,
  Eye,
  Car,
  MessageSquare,
  FileJson,
  Rocket,
  Compass
} from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter) => void;
}

const COLORS = [
  'bg-sky-100 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400',
  'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
  'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400',
  'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
  'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400',
  'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400',
  'bg-pink-100 text-pink-600 dark:bg-pink-900/30 dark:text-pink-400',
  'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
  'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400',
  'bg-slate-100 text-slate-600 dark:bg-slate-800/50 dark:text-slate-400',
  'bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-400',
  'bg-zinc-100 text-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-400',
  'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400',
  'bg-teal-100 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400',
  'bg-gray-100 text-gray-800 dark:bg-gray-800/50 dark:text-gray-300'
];

const ICON_REGISTRY: Record<string, React.ElementType> = {
  Bot, Globe, Code, Image: ImageIcon, Video, FileText, Mic, Users,
  BarChart, ShoppingCart, Database, Search, Server, Eye, Car,
  MessageSquare, FileJson, Rocket, Compass, ChevronRight
};

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const description = adapter.description?.trim();
  const { isDark } = useTheme();
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';

  const handleCardActivate = () => onSelect(adapter);

  const getAgentIconAndColor = (adapter: Adapter) => {
    // Deterministic color fallback
    const hash = adapter.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const colorClass = COLORS[hash % COLORS.length];

    if (adapter.icon && ICON_REGISTRY[adapter.icon]) {
      return { Icon: ICON_REGISTRY[adapter.icon], color: colorClass };
    }

    return { Icon: Bot, color: colorClass };
  };

  const { Icon: IconComponent, color: colorClass } = getAgentIconAndColor(adapter);

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
              <div className="flex items-center gap-2 mb-1">
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${colorClass}`}>
                  <IconComponent className="h-4 w-4" />
                </div>
                <p className="truncate text-[15px] font-semibold text-sky-900 dark:text-sky-300 md:text-base">
                  {adapter.name}
                </p>
              </div>

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
