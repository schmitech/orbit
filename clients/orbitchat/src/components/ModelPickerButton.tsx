import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Search, X } from 'lucide-react';
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

function formatProvider(provider: string): string {
  return provider.replace(/[_-]+/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
}

export function ModelPickerButton({
  availableModels,
  defaultModel,
  selectedModel,
  onSelect,
  wrapperClassName = 'relative hidden md:block',
  maxWidthClass = 'max-w-[220px]',
  triggerTitle,
  listboxLabel,
  staticPaddingClass = 'px-2.5 py-1.5',
  triggerPaddingClass = 'px-2.5 py-1.5',
}: ModelPickerButtonProps) {
  const { t } = useTranslation();
  const resolvedTriggerTitle = triggerTitle ?? t('modelPicker.selectModel');
  const resolvedListboxLabel = listboxLabel ?? t('modelPicker.selectModel');
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [dropdownPos, setDropdownPos] = useState<{ bottom: number; left: number } | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const effectiveModel = selectedModel ?? defaultModel;

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return availableModels;
    return availableModels.filter(model =>
      `${model.name} ${model.provider} ${model.model}`.toLowerCase().includes(normalizedQuery)
    );
  }, [availableModels, query]);

  const selectModel = useCallback((name: string) => {
    onSelect(name);
    setOpen(false);
    setQuery('');
    requestAnimationFrame(() => triggerRef.current?.focus());
  }, [onSelect]);

  const recalcPos = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const menuWidth = Math.min(352, window.innerWidth - 24);
    const rightAlignedLeft = rect.right - menuWidth;
    setDropdownPos({
      bottom: window.innerHeight - rect.top + 10,
      left: Math.min(
        window.innerWidth - menuWidth - 12,
        Math.max(12, rightAlignedLeft)
      ),
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
    const selectedIndex = availableModels.findIndex(model => model.name === effectiveModel);
    setActiveIndex(Math.max(selectedIndex, 0));
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;

    const id = setTimeout(() => searchRef.current?.focus(), 10);

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      const inWrapper = wrapperRef.current?.contains(target) ?? false;
      const inDropdown = dropdownRef.current?.contains(target) ?? false;
      if (!inWrapper && !inDropdown) closeDropdown();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDropdown();
        triggerRef.current?.focus();
        return;
      }
      if (filtered.length === 0) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveIndex(index => (index + 1) % filtered.length);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveIndex(index => (index - 1 + filtered.length) % filtered.length);
      } else if (event.key === 'Home') {
        // In this open combobox, Home/End navigate options rather than moving
        // the search caret so keyboard behavior stays consistent with the list.
        event.preventDefault();
        setActiveIndex(0);
      } else if (event.key === 'End') {
        event.preventDefault();
        setActiveIndex(filtered.length - 1);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        const model = filtered[activeIndex];
        if (model) selectModel(model.name);
      }
    };

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
  }, [activeIndex, closeDropdown, filtered, open, recalcPos, selectModel]);

  useEffect(() => {
    if (!open) return;
    dropdownRef.current
      ?.querySelector<HTMLElement>(`[data-model-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  if (!defaultModel && availableModels.length === 0) return null;

  const dropdown = open && dropdownPos && typeof document !== 'undefined'
    ? createPortal(
        <div
          ref={dropdownRef}
          style={{
            position: 'fixed',
            bottom: dropdownPos.bottom,
            left: dropdownPos.left,
            width: 'min(352px, calc(100vw - 24px))',
            zIndex: 9999,
          }}
          className="overflow-hidden rounded-2xl border border-gray-200/90 bg-white shadow-[0_18px_50px_-12px_rgba(0,0,0,0.3)] ring-1 ring-black/[0.03] dark:border-white/10 dark:bg-[#171717] dark:ring-white/[0.04]"
        >
          <div className="flex items-start justify-between gap-4 px-4 pb-3 pt-4">
            <div>
              <h2 className="text-sm font-semibold leading-5 text-gray-950 dark:text-white">
                {t('modelPicker.chooseModel')}
              </h2>
              <p className="mt-0.5 text-xs leading-4 text-gray-500 dark:text-gray-400">
                {t('modelPicker.chooseModelHint')}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium tabular-nums text-gray-500 dark:bg-white/[0.07] dark:text-gray-400">
                {filtered.length}
              </span>
              <button
                type="button"
                onClick={() => {
                  closeDropdown();
                  requestAnimationFrame(() => triggerRef.current?.focus());
                }}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 transition-colors motion-reduce:transition-none hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:text-gray-500 dark:hover:bg-white/[0.08] dark:hover:text-gray-200 dark:focus-visible:ring-white/20"
                aria-label={t('common.close')}
                title={t('common.close')}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>

          <div className="px-3 pb-3">
            <label className="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-2.5 transition-colors focus-within:border-gray-400 focus-within:bg-white focus-within:ring-2 focus-within:ring-gray-200/70 dark:border-white/10 dark:bg-white/[0.05] dark:focus-within:border-white/25 dark:focus-within:bg-white/[0.07] dark:focus-within:ring-white/10">
              <Search className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={event => {
                  setQuery(event.target.value);
                  setActiveIndex(0);
                }}
                placeholder={t('modelPicker.searchPlaceholder')}
                className="min-w-0 flex-1 appearance-none border-0 bg-transparent p-0 text-sm text-gray-900 shadow-none outline-none ring-0 placeholder:text-gray-400 focus:border-0 focus:outline-none focus:ring-0 dark:text-white dark:placeholder:text-gray-500"
                role="combobox"
                aria-expanded={open}
                aria-haspopup="listbox"
                aria-label={t('modelPicker.searchAriaLabel')}
                aria-controls={listboxId}
                aria-activedescendant={filtered[activeIndex] ? `${listboxId}-option-${activeIndex}` : undefined}
              />
            </label>
          </div>

          <div className="mx-3 border-t border-gray-100 dark:border-white/[0.07]" />
          <div
            id={listboxId}
            role="listbox"
            aria-label={resolvedListboxLabel}
            className="max-h-72 overflow-y-auto p-2"
          >
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center px-4 py-8 text-center">
                <Search className="mb-2 h-5 w-5 text-gray-300 dark:text-gray-600" aria-hidden="true" />
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('modelPicker.noModelsMatch', { query })}
                </p>
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{t('modelPicker.tryAnotherSearch')}</p>
              </div>
            ) : (
              filtered.map((model, index) => {
                const isSelected = effectiveModel === model.name;
                const isActive = activeIndex === index;
                return (
                  <button
                    id={`${listboxId}-option-${index}`}
                    key={model.name}
                    data-model-index={index}
                    role="option"
                    aria-selected={isSelected}
                    type="button"
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => selectModel(model.name)}
                    className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      isActive
                        ? 'bg-gray-100 dark:bg-white/[0.08]'
                        : 'hover:bg-gray-50 dark:hover:bg-white/[0.05]'
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-gray-900 dark:text-gray-100">{model.name}</span>
                      <span className="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">
                        {formatProvider(model.provider)}
                        {model.model !== model.name ? ` · ${model.model}` : ''}
                      </span>
                    </span>
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                      isSelected ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900' : 'text-transparent'
                    }`}>
                      <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
                    </span>
                  </button>
                );
              })
            )}
          </div>

          {filtered.length > 0 && (
            <div className="flex items-center justify-between border-t border-gray-100 bg-gray-50/80 px-4 py-2 text-[11px] text-gray-400 dark:border-white/[0.07] dark:bg-white/[0.025] dark:text-gray-500">
              <span>{t('modelPicker.modelCountHint', { filtered: filtered.length, total: availableModels.length })}</span>
              <span className="hidden sm:inline">{t('modelPicker.keyboardHint')}</span>
            </div>
          )}
        </div>,
        document.body
      )
    : null;

  const label = (
    <span className="min-w-0 flex-1 truncate text-left text-xs font-medium text-gray-800 dark:text-gray-200">
      {effectiveModel ?? t('modelPicker.selectModel')}
    </span>
  );

  return (
    <div ref={wrapperRef} className={wrapperClassName}>
      {availableModels.length > 1 ? (
        <>
          <button
            ref={triggerRef}
            type="button"
            onClick={toggleDropdown}
            className={`group inline-flex h-8 min-w-[124px] ${maxWidthClass} items-center gap-2 rounded-full border border-gray-200 bg-white/80 ${triggerPaddingClass} shadow-sm transition-all motion-reduce:transition-none hover:border-gray-300 hover:bg-white hover:shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:border-white/10 dark:bg-white/[0.05] dark:hover:border-white/20 dark:hover:bg-white/[0.08] dark:focus-visible:ring-white/20`}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={open ? listboxId : undefined}
            title={resolvedTriggerTitle}
          >
            {label}
            <ChevronDown
              className={`h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform duration-200 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
          {dropdown}
        </>
      ) : (
        <div
          className={`inline-flex h-8 min-w-[124px] ${maxWidthClass} items-center gap-2 rounded-full border border-gray-200 bg-white/60 ${staticPaddingClass} shadow-sm dark:border-white/10 dark:bg-white/[0.04]`}
          title={effectiveModel ?? undefined}
        >
          {label}
        </div>
      )}
    </div>
  );
}
