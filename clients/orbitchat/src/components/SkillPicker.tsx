import React from 'react';
import { Check, ImageIcon, Sparkles, Zap } from 'lucide-react';
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
  onActiveSkillChange
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
      <div className="w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg shadow-black/5 dark:border-[#242424] dark:bg-[#101010] dark:shadow-black/30">
        <p className="px-4 py-3 text-sm text-gray-500 dark:text-[#bfc2cd]">No skills available for this adapter.</p>
      </div>
    );
  }

  return (
    <div className="w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg shadow-black/5 dark:border-[#242424] dark:bg-[#101010] dark:shadow-black/30">
      {isLoading ? (
        <div className="px-4 py-3.5">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-[#bfc2cd]">
            <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden="true" />
            Loading skills...
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="px-4 py-3.5">
          <p className="text-sm text-gray-500 dark:text-[#bfc2cd]">
            {normalizedQuery ? `No matching skills for "${query}".` : 'No matching skills.'}
          </p>
        </div>
      ) : (
        <div ref={listRef} role="listbox" aria-label="Available skills" className="max-h-72 overflow-y-auto p-1.5">
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
                <div className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center transition-colors ${
                  isActive
                    ? 'text-gray-900 dark:text-white'
                    : 'text-gray-500 group-hover:text-gray-700 dark:text-[#bfc2cd] dark:group-hover:text-gray-200'
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
    </div>
  );
}
