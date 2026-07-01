import { RefreshCw } from 'lucide-react';
import { getApplicationName } from '../utils/runtimeConfig';
import { PACKAGE_VERSION } from '../utils/version';
import { useTranslation } from 'react-i18next';

export function OutOfServicePage({ message }: { message: string }) {
  const { t } = useTranslation();
  const applicationName = getApplicationName();

  return (
    <main className="min-h-dvh bg-white px-4 py-6 text-slate-950 dark:bg-black dark:text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] w-full max-w-5xl flex-col">
        <header className="flex items-center justify-between gap-4">
          <p className="min-w-0 truncate text-lg font-semibold tracking-tight sm:text-xl">
            {applicationName}
          </p>
          <span className="shrink-0 text-xs font-medium text-slate-400 dark:text-[#858999]">
            v{PACKAGE_VERSION}
          </span>
        </header>

        <section className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-lg space-y-8">
            <div className="flex items-center gap-3">
              <span className="relative flex h-2.5 w-2.5 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-60 dark:bg-amber-500" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500 dark:bg-amber-400" />
              </span>
              <span className="text-xs font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-400">
                {t('outOfService.statusBadge')}
              </span>
            </div>

            <div className="space-y-4">
              <h1 className="text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                {t('outOfService.heading')}
              </h1>
              <p className="max-w-md whitespace-pre-wrap text-base leading-relaxed text-slate-500 dark:text-slate-400">
                {message}
              </p>
            </div>

            <div className="border-t border-slate-200 dark:border-[#242424]" />

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:bg-white dark:text-slate-950 dark:hover:bg-slate-200"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                {t('outOfService.retryButton')}
              </button>
              <span className="hidden text-slate-300 dark:text-slate-700 sm:block" aria-hidden="true">
                ·
              </span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
