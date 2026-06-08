import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { AllowedModel } from '../types';

interface ModelPickerButtonProps {
  availableModels: AllowedModel[];
  defaultModel: string | null;
  selectedModel: string | null;
  onSelect: (name: string) => void;
  wrapperClassName?: string;
  maxWidthClass?: string;
  triggerTitle?: string;
  listboxLabel?: string;
  staticPaddingClass?: string;
  triggerPaddingClass?: string;
}

export function ModelPickerButton({
  availableModels,
  defaultModel,
  selectedModel,
  onSelect,
  wrapperClassName = 'relative hidden md:block',
  maxWidthClass = 'max-w-[140px]',
  triggerTitle = 'Select model',
  listboxLabel = 'Select model',
  staticPaddingClass = 'px-2.5 py-1',
  triggerPaddingClass = 'px-2.5 py-1',
}: ModelPickerButtonProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const effectiveModel = selectedModel ?? defaultModel;

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  if (!defaultModel && availableModels.length === 0) {
    return null;
  }

  return (
    <div ref={wrapperRef} className={wrapperClassName}>
      {availableModels.length > 1 ? (
        <>
          <button
            ref={triggerRef}
            type="button"
            onClick={() => setOpen(value => !value)}
            className={`inline-flex ${maxWidthClass} items-center gap-1 rounded-full border border-gray-200 bg-gray-100 ${triggerPaddingClass} text-xs font-medium text-gray-600 transition-colors hover:bg-gray-200 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd] dark:hover:bg-[#3a3b48]`}
            aria-haspopup="listbox"
            aria-expanded={open}
            title={triggerTitle}
          >
            <span className="truncate">{effectiveModel}</span>
            <ChevronDown
              className={`h-3 w-3 flex-shrink-0 text-gray-400 transition-transform duration-150 dark:text-[#6b6f7a] ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
          {open && (
            <div
              role="listbox"
              aria-label={listboxLabel}
              className="absolute right-0 bottom-full z-50 mb-1.5 min-w-[200px] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg dark:border-[#2f303d] dark:bg-[#111111]"
            >
              {availableModels.map(model => {
                const isActive = effectiveModel === model.name;
                return (
                  <button
                    key={model.name}
                    role="option"
                    aria-selected={isActive}
                    type="button"
                    onClick={() => {
                      onSelect(model.name);
                      setOpen(false);
                      triggerRef.current?.focus();
                    }}
                    className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors ${
                      isActive
                        ? 'bg-gray-100 text-gray-900 dark:bg-[#1f1f1f] dark:text-[#ececf1]'
                        : 'text-gray-700 hover:bg-gray-50 dark:text-[#bfc2cd] dark:hover:bg-[#1a1a1a]'
                    }`}
                  >
                    <span className={`flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-full border ${
                      isActive
                        ? 'border-blue-500 bg-blue-500 dark:border-blue-400 dark:bg-blue-400'
                        : 'border-gray-300 dark:border-[#5a5b65]'
                    }`}>
                      {isActive && (
                        <span className="h-1.5 w-1.5 rounded-full bg-white" />
                      )}
                    </span>
                    <span className="truncate font-medium normal-case tracking-normal">{model.name}</span>
                  </button>
                );
              })}
            </div>
          )}
        </>
      ) : (
        <div
          className={`inline-flex ${maxWidthClass} items-center rounded-full border border-gray-200 bg-gray-100 ${staticPaddingClass} text-xs text-gray-500 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd]`}
          title={effectiveModel ?? undefined}
        >
          <span className="truncate">{effectiveModel}</span>
        </div>
      )}
    </div>
  );
}
