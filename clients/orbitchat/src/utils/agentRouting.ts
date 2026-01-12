import { fetchAdapters, type Adapter } from './middlewareConfig';
import { debugWarn } from './debug';

type AdapterSlugMap = Map<string, string>;

const ADAPTER_CACHE_TTL = 60 * 1000; // 1 minute
let cachedMap: AdapterSlugMap | null = null;
let cacheTimestamp = 0;

const normalizePath = (value: string): string => {
  if (!value || value === '/') {
    return '/';
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return '/';
  }
  const ensureLeading = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  if (ensureLeading === '/') {
    return '/';
  }
  return ensureLeading.endsWith('/') ? ensureLeading.slice(0, -1) : ensureLeading;
};

export const getBasePath = (): string => {
  if (typeof window === 'undefined') {
    return normalizePath(import.meta.env.BASE_URL ?? '/');
  }
  const baseFromEnv = normalizePath(import.meta.env.BASE_URL ?? '/');
  if (typeof document === 'undefined') {
    return baseFromEnv;
  }
  const baseElement = document.querySelector('base[href]');
  if (!baseElement) {
    return baseFromEnv;
  }
  try {
    const url = new URL(baseElement.getAttribute('href') || '/', window.location.origin);
    return normalizePath(url.pathname || baseFromEnv);
  } catch {
    return baseFromEnv;
  }
};

export const slugifyAdapterName = (name: string): string => {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
};

const ensureAdapterSlugMap = async (): Promise<AdapterSlugMap> => {
  const now = Date.now();
  if (cachedMap && now - cacheTimestamp < ADAPTER_CACHE_TTL) {
    return cachedMap;
  }

  let adapters: Adapter[] = [];
  try {
    adapters = await fetchAdapters();
  } catch (error) {
    debugWarn('[agentRouting] Unable to load adapters for slug resolution', error);
  }

  const map: AdapterSlugMap = new Map();
  adapters.forEach(adapter => {
    const slug = slugifyAdapterName(adapter.name);
    if (slug) {
      map.set(slug, adapter.name);
    }
  });

  cachedMap = map;
  cacheTimestamp = now;
  return map;
};

export const getAgentSlugFromPath = (pathname: string): string | null => {
  const normalizedBase = getBasePath();
  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;

  let remainder = normalizedPath;
  if (normalizedBase !== '/') {
    if (!normalizedPath.startsWith(normalizedBase)) {
      return null;
    }
    remainder = normalizedPath.slice(normalizedBase.length);
  }

  const segments = remainder.split('/').filter(Boolean);
  if (segments.length === 0) {
    return null;
  }
  return segments[0]?.toLowerCase() || null;
};

const buildPath = (slug: string | null): string => {
  const basePath = getBasePath();
  if (!slug) {
    return basePath;
  }
  const trimmedSlug = slug.replace(/^\/+|\/+$/g, '');
  if (basePath === '/') {
    return trimmedSlug ? `/${trimmedSlug}` : '/';
  }
  return `${basePath}/${trimmedSlug}`.replace(/\/{2,}/g, '/');
};

export const replaceAgentSlug = (slug: string | null): void => {
  if (typeof window === 'undefined') {
    return;
  }
  const nextPath = buildPath(slug);
  const current = window.location.pathname;
  if (nextPath === current) {
    return;
  }
  const search = window.location.search || '';
  const hash = window.location.hash || '';
  window.history.replaceState(window.history.state, '', `${nextPath}${search}${hash}`);
};

export const resolveAdapterNameFromSlug = async (slug: string): Promise<string | null> => {
  const cleaned = slug.trim().toLowerCase();
  if (!cleaned) {
    return null;
  }

  const map = await ensureAdapterSlugMap();
  return map.get(cleaned) || null;
};

export const resetAdapterSlugCache = (): void => {
  cachedMap = null;
  cacheTimestamp = 0;
};
