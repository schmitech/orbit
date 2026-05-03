import { useState, useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import type { Adapter } from '../utils/middlewareConfig';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';
import { ModelsService } from '../services/modelsService';
import type { AllowedModel } from '../types';

interface AgentCardProps {
  adapter: Adapter;
  onSelect: (adapter: Adapter, model?: string) => void;
}

interface MiniModelPickerProps {
  defaultModel: string | null;
  availableModels: AllowedModel[];
  selectedModel: string | null;
  onSelect: (name: string) => void;
}

function MiniModelPicker({ defaultModel, availableModels, selectedModel, onSelect }: MiniModelPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const displayLabel = selectedModel ?? defaultModel;
  if (!displayLabel) return null;

  if (availableModels.length <= 1) {
    return (
      <span
        className="max-w-full truncate text-xs font-medium text-sky-800 dark:text-sky-300"
        title={displayLabel}
        aria-label={`Model: ${displayLabel}`}
      >
        {displayLabel}
      </span>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="inline-flex max-w-[160px] items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-800 transition-colors hover:border-sky-300 hover:bg-sky-100 dark:border-sky-800/60 dark:bg-sky-950/40 dark:text-sky-300 dark:hover:border-sky-700 dark:hover:bg-sky-900/40"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="block truncate">{displayLabel}</span>
        <svg
          className={`h-3 w-3 flex-shrink-0 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"
        >
          <path d="M2 4l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Select model"
          className="absolute right-0 top-full z-50 mt-1.5 min-w-[160px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-[#4a4b54] dark:bg-[#2a2b38]"
        >
          {availableModels.map(m => {
            const isActive = (selectedModel ?? defaultModel) === m.name;
            return (
              <button
                key={m.name}
                role="option"
                aria-selected={isActive}
                type="button"
                onClick={() => { onSelect(m.name); setOpen(false); }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors ${
                  isActive
                    ? 'bg-sky-50 text-sky-900 dark:bg-sky-950/50 dark:text-sky-200'
                    : 'text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-[#313240]'
                }`}
              >
                <span className={`flex h-3 w-3 flex-shrink-0 items-center justify-center rounded-full border ${
                  isActive ? 'border-sky-500 bg-sky-500' : 'border-slate-300 dark:border-[#5a5b65]'
                }`}>
                  {isActive && <svg className="h-2 w-2 text-white" viewBox="0 0 8 8" fill="currentColor"><circle cx="4" cy="4" r="2" /></svg>}
                </span>
                <span className="truncate font-medium">{m.name}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AgentCard({ adapter, onSelect }: AgentCardProps) {
  const description = adapter.description?.trim();
  const defaultModel = adapter.model?.trim() ?? null;
  const { isDark } = useTheme();
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';

  const [availableModels, setAvailableModels] = useState<AllowedModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    ModelsService.listAdapterModels(adapter.id, adapter.id).then(models => {
      if (cancelled) return;
      setAvailableModels(models);
      if (models.length > 0) setSelectedModel(models[0].name);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [adapter.id]);

  const handleCardActivate = () => onSelect(adapter, selectedModel ?? undefined);

  const stopBubble = (e: React.MouseEvent | React.KeyboardEvent) => e.stopPropagation();

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

            {/* Desktop right column: model picker + chevron */}
            <div className="hidden min-w-[132px] flex-shrink-0 flex-col items-end gap-3 self-stretch md:flex">
              <div onClick={stopBubble} onKeyDown={stopBubble}>
                <MiniModelPicker
                  defaultModel={defaultModel}
                  availableModels={availableModels}
                  selectedModel={selectedModel}
                  onSelect={setSelectedModel}
                />
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCardActivate();
                }}
                className="mt-auto inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-700 transition-all duration-150 hover:bg-slate-100 group-hover:translate-x-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/30 dark:text-slate-200 dark:hover:bg-white/10 dark:focus-visible:ring-sky-400/30"
                aria-label={`Start conversation with ${adapter.name}`}
              >
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile bottom row */}
      <div className="mt-3 flex items-center justify-between gap-3 border-t border-slate-200 pt-2.5 text-xs text-slate-500 dark:border-white/10 dark:text-slate-400 md:hidden">
        <div onClick={stopBubble} onKeyDown={stopBubble}>
          <MiniModelPicker
            defaultModel={defaultModel}
            availableModels={availableModels}
            selectedModel={selectedModel}
            onSelect={setSelectedModel}
          />
        </div>
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
