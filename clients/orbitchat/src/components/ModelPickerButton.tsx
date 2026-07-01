import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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
  maxWidthClass = 'max-w-[200px]',
  triggerTitle,
  listboxLabel,
  staticPaddingClass = 'px-3 py-1.5',
  triggerPaddingClass = 'px-3 py-1.5',
}: ModelPickerButtonProps) {
  const { t } = useTranslation();
  const resolvedTriggerTitle = triggerTitle ?? t('modelPicker.selectModel');
  const resolvedListboxLabel = listboxLabel ?? t('modelPicker.selectModel');
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dropdownPos, setDropdownPos] = useState<{ bottom: number; right: number } | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const effectiveModel = selectedModel ?? defaultModel;

  const filtered = query.trim()
    ? availableModels.filter(m => m.name.toLowerCase().includes(query.trim().toLowerCase()))
    : availableModels;

  const recalcPos = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setDropdownPos({
      bottom: window.innerHeight - rect.top + 8,
      right: window.innerWidth - rect.right,
    });
  }, []);

  const closeDropdown = useCallback(() => {
    setOpen(false);
    setQuery('');
  }, []);

  const toggleDropdown = () => {
    if (open) {
      closeDropdown();
      return;
    }
    recalcPos();
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;

    const id = setTimeout(() => searchRef.current?.focus(), 10);

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      const inWrapper = wrapperRef.current?.contains(target) ?? false;
      const inDropdown = dropdownRef.current?.contains(target) ?? false;
      if (!inWrapper && !inDropdown) {
        closeDropdown();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDropdown();
        triggerRef.current?.focus();
      }
    };

    // Keep position in sync while open
    const resizeObserver = new ResizeObserver(recalcPos);
    if (triggerRef.current) resizeObserver.observe(triggerRef.current);
    window.addEventListener('resize', recalcPos, { passive: true });
    document.addEventListener('scroll', recalcPos, { capture: true, passive: true });

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(id);
      resizeObserver.disconnect();
      window.removeEventListener('resize', recalcPos);
      document.removeEventListener('scroll', recalcPos, { capture: true });
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeDropdown, open, recalcPos]);

  if (!defaultModel && availableModels.length === 0) {
    return null;
  }

  const dropdown = open && dropdownPos && typeof document !== 'undefined'
    ? createPortal(
        <div
          ref={dropdownRef}
          style={{ position: 'fixed', bottom: dropdownPos.bottom, right: dropdownPos.right, width: 288, zIndex: 9999 }}
          className="rounded-xl border border-gray-200 bg-white shadow-xl dark:border-[#2f303d] dark:bg-[#111111]"
        >
          {/* Search bar */}
          <div className="p-2 border-b border-gray-100 dark:border-[#222222]">
            <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-1.5 dark:bg-[#1a1a1a]">
              <Search className="h-3.5 w-3.5 flex-shrink-0 text-gray-400 dark:text-[#6b6f7a]" aria-hidden="true" />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder={t('modelPicker.searchPlaceholder')}
                className="flex-1 bg-transparent pl-1 text-xs text-gray-700 placeholder-gray-400 focus:outline-none dark:text-[#ececf1] dark:placeholder-[#6b6f7a]"
                aria-label={t('modelPicker.searchAriaLabel')}
              />
            </div>
          </div>

          {/* Model list */}
          <div
            role="listbox"
            aria-label={resolvedListboxLabel}
            className="max-h-60 overflow-y-auto py-1"
          >
            {filtered.length === 0 ? (
              <div className="px-3 py-5 text-center text-xs text-gray-400 dark:text-[#6b6f7a]">
                {t('modelPicker.noModelsMatch', { query })}
              </div>
            ) : (
              filtered.map(model => {
                const isActive = effectiveModel === model.name;
                return (
                  <button
                    key={model.name}
                    role="option"
                    aria-selected={isActive}
                    type="button"
                    onClick={() => {
                      onSelect(model.name);
                      closeDropdown();
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
              })
            )}
          </div>

          {/* Count hint when list is long */}
          {availableModels.length > 8 && (
            <div className="border-t border-gray-100 px-3 py-1.5 dark:border-[#222222]">
              <span className="text-[10px] text-gray-400 dark:text-[#6b6f7a]">
                {t('modelPicker.modelCountHint', { filtered: filtered.length, total: availableModels.length })}
              </span>
            </div>
          )}
        </div>,
        document.body
      )
    : null;

  return (
    <div ref={wrapperRef} className={wrapperClassName}>
      {availableModels.length > 1 ? (
        <>
          <button
            ref={triggerRef}
            type="button"
            onClick={toggleDropdown}
            className={`inline-flex min-w-[100px] ${maxWidthClass} items-center gap-1.5 rounded-full border border-gray-200 bg-gray-100 ${triggerPaddingClass} text-xs font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd] dark:hover:bg-[#3a3b48]`}
            aria-haspopup="listbox"
            aria-expanded={open}
            title={resolvedTriggerTitle}
          >
            <span className="truncate flex-1">{effectiveModel}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 flex-shrink-0 text-gray-400 transition-transform duration-150 dark:text-[#6b6f7a] ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
          {dropdown}
        </>
      ) : (
        <div
          className={`inline-flex min-w-[100px] ${maxWidthClass} items-center rounded-full border border-gray-200 bg-gray-100 ${staticPaddingClass} text-xs text-gray-500 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd]`}
          title={effectiveModel ?? undefined}
        >
          <span className="truncate">{effectiveModel}</span>
        </div>
      )}
    </div>
  );
}
