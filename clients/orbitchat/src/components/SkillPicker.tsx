import React from 'react';
import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SkillInfo } from '../types';

interface SkillPickerProps {
  skills: SkillInfo[];
  isLoading: boolean;
  selectedSkill: SkillInfo | null;
  activeSkillName?: string | null;
  query?: string;
  onSelect: (skill: SkillInfo) => void;
  onActiveSkillChange?: (skill: SkillInfo) => void;
  onClose: () => void;
}

function formatSkillName(skillName: string) {
  return skillName.replace(/-/g, ' ');
}

export function SkillPicker({
  skills,
  isLoading,
  selectedSkill,
  activeSkillName,
  query = '',
  onSelect,
  onActiveSkillChange
}: SkillPickerProps) {
  const { t } = useTranslation();
  const listRef = React.useRef<HTMLDivElement | null>(null);
  const normalizedQuery = query.toLowerCase().replace(/-/g, ' ');
  const filteredSkills = normalizedQuery
    ? skills.filter(s =>
        s.name.replace(/-/g, ' ').toLowerCase().includes(normalizedQuery) ||
        s.description.toLowerCase().includes(normalizedQuery)
      )
    : skills;

  React.useEffect(() => {
    const activeOption = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    activeOption?.scrollIntoView({ block: 'nearest' });
  }, [activeSkillName, filteredSkills.length]);

  if (!isLoading && skills.length === 0) {
    return (
      <div className="w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg shadow-black/5 dark:border-[#242424] dark:bg-[#101010] dark:shadow-black/30">
        <p className="px-4 py-3 text-sm text-gray-500 dark:text-[#bfc2cd]">{t('skillPicker.noSkillsAvailable')}</p>
      </div>
    );
  }

  return (
    <div className="w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg shadow-black/5 dark:border-[#242424] dark:bg-[#101010] dark:shadow-black/30">
      {isLoading ? (
        <div className="px-4 py-3.5">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-[#bfc2cd]">
            <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden="true" />
            {t('skillPicker.loadingLabel')}
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="px-4 py-3.5">
          <p className="text-sm text-gray-500 dark:text-[#bfc2cd]">
            {normalizedQuery ? t('skillPicker.noMatchingSkills', { query }) : t('skillPicker.noMatchingSkillsGeneric')}
          </p>
        </div>
      ) : (
        <div ref={listRef} role="listbox" aria-label={t('skillPicker.listboxLabel')} className="max-h-72 overflow-y-auto p-1.5">
          {filteredSkills.map((skill, index) => {
            const isSelected = selectedSkill?.name === skill.name;
            const isActive =
              activeSkillName === skill.name ||
              (!activeSkillName && (isSelected || (!selectedSkill && index === 0)));
            return (
              <button
                key={skill.name}
                id={`skill-option-${skill.name}`}
                type="button"
                role="option"
                aria-selected={isActive}
                data-active={isActive ? 'true' : undefined}
                onMouseEnter={() => onActiveSkillChange?.(skill)}
                onClick={() => onSelect(skill)}
                className={`group flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:focus-visible:ring-gray-600 ${
                  isActive
                    ? 'bg-gray-100 text-gray-950 dark:bg-[#242424] dark:text-white'
                    : 'text-gray-900 hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-[#1a1a1a]'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium capitalize leading-5 text-current">
                      {formatSkillName(skill.name)}
                    </span>
                  </div>
                  {skill.description && (
                    <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-[#bfc2cd]">{skill.description}</p>
                  )}
                </div>
                {isSelected && (
                  <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white dark:bg-white dark:text-gray-900">
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {/* One hint, not a legend: arrows and Enter are already implied by a
          highlighted list. The slash is the thing nobody can guess, and this is
          where people who arrived by tapping the Skills button learn it. */}
      {!isLoading && filteredSkills.length > 0 && (
        <div className="flex items-center gap-1 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-500 dark:border-[#1f1f1f] dark:text-[#8b8b99]">
          <KeyCap>/</KeyCap>
          {t('skillPicker.footer.slashAnytime')}
        </div>
      )}
    </div>
  );
}

/**
 * A keycap, not a glyph: the raised bottom border is what reads as "this is a key
 * you press". Shared by the picker footer, the Skills buttons, and the composer
 * placeholder hint so every surface teaches the shortcut in the same language.
 * The glyph inherits `currentColor`, so a keycap always matches the text it sits
 * in — muted inside a placeholder, full strength inside a button.
 *
 * `align-middle` centres the cap on the surrounding text's optical centre
 * (baseline + half x-height) when it sits in a run of inline text; flex parents
 * such as the picker footer and the Skills button ignore it and centre it
 * themselves.
 */
export function KeyCap({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex h-[17px] min-w-[17px] items-center justify-center rounded border border-gray-300 border-b-2 bg-white px-1 align-middle font-mono text-[10px] leading-none text-current dark:border-[#3a3a3a] dark:bg-[#1f1f1f] ${className}`}
      aria-hidden="true"
    >
      {children}
    </span>
  );
}
