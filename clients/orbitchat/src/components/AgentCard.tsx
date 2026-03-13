import { ChevronRight } from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter) => void;
}

const ACCENT_STYLES = [
  {
    barLight: 'from-[#e7c77c] via-[#d79b5d] to-[#8a5a36]',
    barDark: 'from-[#f0d38a] via-[#c68855] to-[#6e4732]',
    haloLight: 'from-[#f3d89a]/35 via-[#e5b47a]/18 to-transparent',
    haloDark: 'from-[#d8a45c]/22 via-[#8d5a3c]/12 to-transparent',
    border: 'hover:border-[#d9b06b]/70 dark:hover:border-[#b98352]/28',
    ring: 'group-hover:ring-[#efd7ae]/70 dark:group-hover:ring-[#b98352]/18'
  },
  {
    barLight: 'from-[#9ad1d4] via-[#4e9bb7] to-[#2f5f83]',
    barDark: 'from-[#8cc6cf] via-[#4b87a4] to-[#274664]',
    haloLight: 'from-[#a9dde0]/34 via-[#65acc3]/18 to-transparent',
    haloDark: 'from-[#5ca6bb]/22 via-[#305f81]/12 to-transparent',
    border: 'hover:border-[#7eb9c6]/70 dark:hover:border-[#4e8ca7]/28',
    ring: 'group-hover:ring-[#cde7ea]/65 dark:group-hover:ring-[#4e8ca7]/18'
  },
  {
    barLight: 'from-[#8dc7a3] via-[#4d9078] to-[#27574b]',
    barDark: 'from-[#82b79c] via-[#447762] to-[#203f37]',
    haloLight: 'from-[#9fd3af]/34 via-[#6aa48b]/18 to-transparent',
    haloDark: 'from-[#5a9c7f]/22 via-[#285345]/12 to-transparent',
    border: 'hover:border-[#79b08c]/70 dark:hover:border-[#53896f]/28',
    ring: 'group-hover:ring-[#d3eadb]/65 dark:group-hover:ring-[#53896f]/18'
  },
  {
    barLight: 'from-[#d8a6a0] via-[#a56e75] to-[#65414d]',
    barDark: 'from-[#c99893] via-[#8f5d63] to-[#553640]',
    haloLight: 'from-[#ddb1ab]/32 via-[#b67d85]/18 to-transparent',
    haloDark: 'from-[#aa6f76]/22 via-[#603b46]/12 to-transparent',
    border: 'hover:border-[#c28a8a]/70 dark:hover:border-[#915c63]/28',
    ring: 'group-hover:ring-[#ebd0cb]/65 dark:group-hover:ring-[#915c63]/18'
  },
  {
    barLight: 'from-[#b9c3e7] via-[#6e81bb] to-[#394a84]',
    barDark: 'from-[#aab7de] via-[#6272a5] to-[#2e3c67]',
    haloLight: 'from-[#c4cef0]/34 via-[#7f92c8]/18 to-transparent',
    haloDark: 'from-[#7484bc]/22 via-[#374773]/12 to-transparent',
    border: 'hover:border-[#8e9ecc]/70 dark:hover:border-[#6676a8]/28',
    ring: 'group-hover:ring-[#dde3f6]/65 dark:group-hover:ring-[#6676a8]/18'
  },
  {
    barLight: 'from-[#d6c8a7] via-[#9e8b63] to-[#5f5038]',
    barDark: 'from-[#cab98e] via-[#8f7950] to-[#4f412c]',
    haloLight: 'from-[#e0d2b2]/34 via-[#b0996b]/18 to-transparent',
    haloDark: 'from-[#a78956]/22 via-[#5f4d32]/12 to-transparent',
    border: 'hover:border-[#b79e6f]/70 dark:hover:border-[#8b744a]/28',
    ring: 'group-hover:ring-[#ece2ca]/65 dark:group-hover:ring-[#8b744a]/18'
  },
  {
    barLight: 'from-[#b6d4cc] via-[#688f8b] to-[#3a5558]',
    barDark: 'from-[#a7c6bf] via-[#5a7d79] to-[#2c4345]',
    haloLight: 'from-[#c2ddd6]/34 via-[#7aa4a0]/18 to-transparent',
    haloDark: 'from-[#6d9790]/22 via-[#38585a]/12 to-transparent',
    border: 'hover:border-[#86aaa4]/70 dark:hover:border-[#628781]/28',
    ring: 'group-hover:ring-[#dcece8]/65 dark:group-hover:ring-[#628781]/18'
  },
  {
    barLight: 'from-[#d8c0df] via-[#8e6d9d] to-[#4d3c5c]',
    barDark: 'from-[#c9afd3] via-[#775c88] to-[#3f304d]',
    haloLight: 'from-[#decae5]/34 via-[#9d80ac]/18 to-transparent',
    haloDark: 'from-[#8d6ca1]/22 via-[#4e3c5f]/12 to-transparent',
    border: 'hover:border-[#a98bb9]/70 dark:hover:border-[#7e6390]/28',
    ring: 'group-hover:ring-[#eadff0]/65 dark:group-hover:ring-[#7e6390]/18'
  },
  {
    barLight: 'from-[#d9b7a2] via-[#b07257] to-[#6b4132]',
    barDark: 'from-[#cea48a] via-[#986046] to-[#563327]',
    haloLight: 'from-[#e2c1ae]/34 via-[#c38769]/18 to-transparent',
    haloDark: 'from-[#b67558]/22 via-[#6a4332]/12 to-transparent',
    border: 'hover:border-[#c38a6e]/70 dark:hover:border-[#9d6248]/28',
    ring: 'group-hover:ring-[#efd9cb]/65 dark:group-hover:ring-[#9d6248]/18'
  },
  {
    barLight: 'from-[#b8d7df] via-[#5d8fa4] to-[#314e65]',
    barDark: 'from-[#a7c6d0] via-[#527d91] to-[#263d50]',
    haloLight: 'from-[#c6e1e7]/34 via-[#70a4b9]/18 to-transparent',
    haloDark: 'from-[#608ea2]/22 via-[#33546a]/12 to-transparent',
    border: 'hover:border-[#7fa9ba]/70 dark:hover:border-[#5b8698]/28',
    ring: 'group-hover:ring-[#dcebf0]/65 dark:group-hover:ring-[#5b8698]/18'
  },
  {
    barLight: 'from-[#c9d4b3] via-[#80935d] to-[#4b5734]',
    barDark: 'from-[#bcc7a5] via-[#71804f] to-[#394327]',
    haloLight: 'from-[#d6dfc1]/34 via-[#92a56d]/18 to-transparent',
    haloDark: 'from-[#80905c]/22 via-[#485335]/12 to-transparent',
    border: 'hover:border-[#97a873]/70 dark:hover:border-[#718050]/28',
    ring: 'group-hover:ring-[#e5ebd8]/65 dark:group-hover:ring-[#718050]/18'
  },
  {
    barLight: 'from-[#d4bcc6] via-[#8f6b79] to-[#533943]',
    barDark: 'from-[#c8aeb9] via-[#7a5966] to-[#442f38]',
    haloLight: 'from-[#ddc8d0]/34 via-[#9f7b89]/18 to-transparent',
    haloDark: 'from-[#8b6774]/22 via-[#533943]/12 to-transparent',
    border: 'hover:border-[#a88794]/70 dark:hover:border-[#7d5c68]/28',
    ring: 'group-hover:ring-[#eadde2]/65 dark:group-hover:ring-[#7d5c68]/18'
  }
] as const;

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const description = adapter.description?.trim();
  const model = adapter.model?.trim();
  const accent = ACCENT_STYLES[hashString(adapter.id || adapter.name) % ACCENT_STYLES.length];
  const { isDark } = useTheme();
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';
  const barGradientClass = isDark ? accent.barDark : accent.barLight;
  const haloGradientClass = isDark ? accent.haloDark : accent.haloLight;
  const hoverBackgroundClass = isDark
    ? 'group-hover:bg-[linear-gradient(180deg,rgba(255,255,255,0.035),rgba(255,255,255,0.015))]'
    : 'group-hover:bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.96))]';

  return (
    <button
      type="button"
      data-agent-card="true"
      onClick={() => onSelect(adapter)}
      className={`group relative flex w-full flex-col overflow-hidden rounded-[1.6rem] border border-gray-200/90 bg-white/[0.96] p-4 text-left shadow-[0_10px_30px_rgba(15,23,42,0.06)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_20px_55px_rgba(15,23,42,0.14)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500/35 active:scale-[0.992] dark:border-[#3b3c49] dark:bg-[#23242c]/95 dark:shadow-[0_12px_35px_rgba(0,0,0,0.22)] ${accent.border} ${accent.ring} dark:focus-visible:border-blue-300 dark:focus-visible:ring-blue-300/35 md:gap-4 md:p-5`}
    >
      <div className={`pointer-events-none absolute right-0 top-0 h-28 w-28 rounded-full bg-gradient-to-br opacity-70 blur-2xl transition-opacity duration-200 group-hover:opacity-100 ${haloGradientClass}`} />
      <div className={`pointer-events-none absolute inset-0 transition-all duration-200 ${hoverBackgroundClass} bg-[linear-gradient(180deg,rgba(255,255,255,0.38),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.025),rgba(255,255,255,0))]`} />

      <div className="relative flex items-center gap-3 md:gap-4">
        <div className={`h-10 w-1.5 flex-shrink-0 rounded-full bg-gradient-to-b ${barGradientClass}`} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-semibold tracking-[-0.01em] text-gray-950 dark:text-white md:text-lg">
                {adapter.name}
              </p>
            </div>

            {model && (
              <span
                className="hidden max-w-[48%] flex-shrink-0 truncate rounded-full border border-gray-200/90 bg-white/85 px-2.5 py-1 text-[11px] font-medium tracking-wide text-gray-600 shadow-sm dark:border-white/10 dark:bg-white/5 dark:text-gray-300 md:inline"
                title={model}
                aria-label={`Model: ${model}`}
              >
                {model}
              </span>
            )}
          </div>

          {model && (
            <span
              className="mt-2 inline-flex max-w-full truncate rounded-full border border-gray-200/90 bg-white/85 px-2.5 py-1 text-[11px] font-medium tracking-wide text-gray-600 shadow-sm dark:border-white/10 dark:bg-white/5 dark:text-gray-300 md:hidden"
              title={model}
              aria-label={`Model: ${model}`}
            >
              {model}
            </span>
          )}
        </div>

        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border border-gray-200/80 bg-white/90 text-gray-400 shadow-sm transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-gray-700 dark:border-white/10 dark:bg-white/5 dark:text-gray-500 dark:group-hover:text-white md:h-11 md:w-11">
          <ChevronRight className="h-4 w-4 md:h-5 md:w-5" />
        </div>
      </div>

      {description ? (
        <div className="agent-card-description relative mt-3 text-sm leading-relaxed text-gray-600 dark:text-gray-200 md:mt-4 md:text-[0.95rem]">
          <MarkdownRenderer
            content={description}
            className="prose prose-slate max-w-none text-inherit dark:prose-invert [&>*]:mb-0 [&>*]:mt-0 [&_p]:overflow-hidden [&_p]:text-ellipsis [&_p]:[display:-webkit-box] [&_p]:[-webkit-box-orient:vertical] [&_p]:[-webkit-line-clamp:3]"
            syntaxTheme={syntaxTheme}
          />
        </div>
      ) : (
        <p className="relative mt-3 text-sm text-gray-500 dark:text-gray-400 md:mt-4 md:text-[0.95rem]">
          Configure this agent to see its capabilities.
        </p>
      )}
    </button>
  );
}
