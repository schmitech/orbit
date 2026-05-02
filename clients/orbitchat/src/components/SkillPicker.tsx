import React from 'react';
import { Sparkles, ImageIcon, X, Zap } from 'lucide-react';
import type { SkillInfo } from '../types';

interface SkillPickerProps {
  skills: SkillInfo[];
  isLoading: boolean;
  selectedSkill: SkillInfo | null;
  query?: string;
  onSelect: (skill: SkillInfo) => void;
  onClose: () => void;
}

function getSkillIcon(skillName: string) {
  if (skillName.includes('image')) {
    return <ImageIcon className="h-4 w-4 flex-shrink-0" />;
  }
  if (skillName.includes('video') || skillName.includes('audio')) {
    return <Zap className="h-4 w-4 flex-shrink-0" />;
  }
  return <Sparkles className="h-4 w-4 flex-shrink-0" />;
}

export function SkillPicker({ skills, isLoading, selectedSkill, query = '', onSelect, onClose }: SkillPickerProps) {
  const normalizedQuery = query.toLowerCase().replace(/-/g, ' ');
  const filteredSkills = normalizedQuery
    ? skills.filter(s =>
        s.name.replace(/-/g, ' ').toLowerCase().includes(normalizedQuery) ||
        s.description.toLowerCase().includes(normalizedQuery)
      )
    : skills;

  if (!isLoading && skills.length === 0) {
    return (
      <div className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 dark:border-[#40414f] dark:bg-[#2d2f39]">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-[#8e8ea0]">Skills</span>
          <button
            type="button"
            onClick={onClose}
            className="flex h-5 w-5 items-center justify-center rounded text-gray-400 hover:text-gray-600 dark:text-[#6b6f7a] dark:hover:text-[#bfc2cd] transition-colors"
            aria-label="Close skills picker"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-[#8e8ea0]">No skills available for this adapter.</p>
      </div>
    );
  }

  return (
    <div className="w-full rounded-lg border border-gray-200 bg-white dark:border-[#40414f] dark:bg-[#2d2f39] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-[#3c3f4a]">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-violet-500 dark:text-violet-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-[#8e8ea0]">Skills</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-5 w-5 items-center justify-center rounded text-gray-400 hover:text-gray-600 dark:text-[#6b6f7a] dark:hover:text-[#bfc2cd] transition-colors"
          aria-label="Close skills picker"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {isLoading ? (
        <div className="px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-[#8e8ea0]">
            <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
            Loading skills...
          </div>
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="px-4 py-3">
          <p className="text-sm text-gray-500 dark:text-[#8e8ea0]">No matching skills.</p>
        </div>
      ) : (
        <div role="listbox" aria-label="Available skills">
          {filteredSkills.map((skill) => {
            const isSelected = selectedSkill?.name === skill.name;
            return (
              <button
                key={skill.name}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => onSelect(skill)}
                className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${
                  isSelected
                    ? 'bg-violet-50 dark:bg-violet-900/20'
                    : 'hover:bg-gray-50 dark:hover:bg-[#3c3f4a]'
                }`}
              >
                <div className={`mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${
                  isSelected
                    ? 'bg-violet-100 text-violet-600 dark:bg-violet-800/40 dark:text-violet-300'
                    : 'bg-gray-100 text-gray-500 dark:bg-[#3c3f4a] dark:text-[#bfc2cd]'
                }`}>
                  {getSkillIcon(skill.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium capitalize ${
                      isSelected
                        ? 'text-violet-700 dark:text-violet-300'
                        : 'text-[#353740] dark:text-[#ececf1]'
                    }`}>
                      {skill.name.replace(/-/g, ' ')}
                    </span>
                    {isSelected && (
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-500 dark:text-violet-400">Active</span>
                    )}
                  </div>
                  {skill.description && (
                    <p className="mt-0.5 text-xs text-gray-500 dark:text-[#8e8ea0] line-clamp-2">{skill.description}</p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
