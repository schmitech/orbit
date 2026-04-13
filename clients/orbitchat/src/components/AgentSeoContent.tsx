import { MarkdownRenderer } from './markdown';
import type { SeoAdapter } from '../utils/seo';

interface AgentSeoContentProps {
  adapter: SeoAdapter;
  syntaxTheme: 'dark' | 'light';
  forcedThemeClass?: string;
}

export function AgentSeoContent({ adapter, syntaxTheme, forcedThemeClass = '' }: AgentSeoContentProps) {
  const notes = adapter.notes?.trim();

  if (!notes) {
    return null;
  }

  return (
    <section
      aria-labelledby="agent-seo-content-title"
      className="mx-auto w-full max-w-[56rem] px-1 text-left sm:px-0"
    >
      <h2 id="agent-seo-content-title" className="sr-only">
        {adapter.name}
      </h2>
      <div>
        <MarkdownRenderer
          content={notes}
          className={`message-markdown prose prose-slate dark:prose-invert max-w-none text-sm leading-relaxed text-[#434654] dark:text-[#d7dae3] [&>:first-child]:mt-0 [&>:last-child]:mb-0 ${forcedThemeClass}`}
          syntaxTheme={syntaxTheme}
        />
      </div>
    </section>
  );
}
