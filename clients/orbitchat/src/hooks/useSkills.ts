import { useState, useEffect, useRef, useCallback } from 'react';
import type { SkillInfo } from '../types';
import { SkillsService } from '../services/skillsService';
import { debugLog, debugWarn } from '../utils/debug';

const CACHE_TTL_MS = 60_000;

interface CacheEntry {
  skills: SkillInfo[];
  expiresAt: number;
}

const skillsCache = new Map<string, CacheEntry>();

export interface UseSkillsOptions {
  adapterName?: string | null;
  enabled?: boolean;
  /**
   * When true (adapter supports conversation threading), skills are suppressed
   * in the main conversation. They are only meaningful inside a thread where
   * retrieved data is already available.
   */
  supportsThreading?: boolean;
}

export interface UseSkillsResult {
  skills: SkillInfo[];
  isLoading: boolean;
  selectedSkill: SkillInfo | null;
  selectSkill: (skill: SkillInfo | null) => void;
  clearSkill: () => void;
}

export function useSkills(options: UseSkillsOptions = {}): UseSkillsResult {
  const { adapterName, enabled = true, supportsThreading = false } = options;
  // Skills are suppressed at the top-level conversation for threading adapters —
  // the user must be inside a thread (where data already exists) to invoke a skill.
  const isActive = enabled && Boolean(adapterName) && !supportsThreading;

  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadedAdapterName, setLoadedAdapterName] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchSkills = useCallback(async (adapter: string) => {
    const cacheKey = adapter;
    const cached = skillsCache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      setSkills(cached.skills);
      setLoadedAdapterName(adapter);
      return;
    }

    if (abortRef.current) {
      abortRef.current.abort();
    }
    abortRef.current = new AbortController();

    setIsLoading(true);
    try {
      const [availableNames, allSkills] = await Promise.all([
        SkillsService.getAdapterSkills(adapter, adapter),
        SkillsService.getAllSkills(adapter),
      ]);

      if (abortRef.current?.signal.aborted) return;

      const available = allSkills.filter(s => availableNames.includes(s.name) && s.enabled);
      skillsCache.set(cacheKey, { skills: available, expiresAt: Date.now() + CACHE_TTL_MS });
      setSkills(available);
      setLoadedAdapterName(adapter);
      debugLog('[useSkills] Loaded', available.length, 'skills for adapter', adapter);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      debugWarn('[useSkills] Failed to load skills:', err instanceof Error ? err.message : String(err));
      setSkills([]);
      setLoadedAdapterName(adapter);
    } finally {
      if (!abortRef.current?.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled || !adapterName) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void fetchSkills(adapterName);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
      abortRef.current?.abort();
    };
  }, [enabled, adapterName, fetchSkills]);

  const selectSkill = useCallback((skill: SkillInfo | null) => {
    setSelectedSkill(skill);
  }, []);

  const clearSkill = useCallback(() => {
    setSelectedSkill(null);
  }, []);

  return {
    skills: isActive && loadedAdapterName === adapterName ? skills : [],
    isLoading: isActive ? (isLoading || loadedAdapterName !== adapterName) : false,
    selectedSkill,
    selectSkill,
    clearSkill,
  };
}
