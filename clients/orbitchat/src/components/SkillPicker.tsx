import React from 'react';
import { Check, ImageIcon, Sparkles, X, Zap } from 'lucide-react';
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

function getSkillIcon(skillName: string) {
  if (skillName.includes('image')) {
    return <ImageIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />;
  }
  if (skillName.includes('video') || skillName.includes('audio')) {
    return <Zap className="h-4 w-4 flex-shrink-0" aria-hidden="true" />;
  }
  return <Sparkles className="h-4 w-4 flex-shrink-0" aria-hidden="true" />;
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
  onActiveSkillChange,
  onClose
}: SkillPickerProps) {
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
      <div className="w-full overflow-hidden rounded-2xl border border-gray-200/80 bg-white shadow-lg shadow-black/5 ring-1 ring-black/[0.03] dark:border-white/10 dark:bg-[#1f1f1f] dark:shadow-black/30 dark:ring-white/[0.03]">
        <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5 dark:border-white/10">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-200">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
            <span className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">Skills</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100 dark:focus-visible:ring-gray-600"
            aria-label="Close skills picker"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <p className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">No skills available for this adapter.</p>
      </div>
    );
  }

  return (
    <div className="w-full overflow-hidden rounded-2xl border border-gray-200/80 bg-white shadow-lg shadow-black/5 ring-1 ring-black/[0.03] dark:border-white/10 dark:bg-[#1f1f1f] dark:shadow-black/30 dark:ring-white/[0.03]">
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5 dark:border-white/10">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-200">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100">Skills</p>
            {normalizedQuery && (
              <p className="truncate text-xs leading-4 text-gray-500 dark:text-gray-400">
                Matching "{query}"
              </p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100 dark:focus-visible:ring-gray-600"
          aria-label="Close skills picker"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {isLoading ? (
        <div className="px-4 py-3.5">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden="true" />
            Loading skills...
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="px-4 py-3.5">
          <p className="text-sm text-gray-500 dark:text-gray-400">No matching skills.</p>
        </div>
      ) : (
        <div ref={listRef} role="listbox" aria-label="Available skills" className="max-h-72 overflow-y-auto p-1.5">
          {filteredSkills.map((skill) => {
            const isSelected = selectedSkill?.name === skill.name;
            const isActive = activeSkillName === skill.name || (!activeSkillName && isSelected);
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
                className={`group flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:focus-visible:ring-gray-600 ${
                  isActive
                    ? 'bg-gray-100 text-gray-950 dark:bg-white/10 dark:text-white'
                    : 'text-gray-900 hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-white/[0.06]'
                }`}
              >
                <div className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg transition-colors ${
                  isActive
                    ? 'bg-white text-gray-900 shadow-sm dark:bg-white/15 dark:text-white dark:shadow-none'
                    : 'bg-gray-100 text-gray-500 group-hover:text-gray-700 dark:bg-white/[0.08] dark:text-gray-400 dark:group-hover:text-gray-200'
                }`}>
                  {getSkillIcon(skill.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium capitalize leading-5 text-current">
                      {formatSkillName(skill.name)}
                    </span>
                  </div>
                  {skill.description && (
                    <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400">{skill.description}</p>
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
    </div>
  );
}
