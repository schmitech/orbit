import { getApplicationDescription, getApplicationName, getSeoAlternateSiteUrls, getSeoExposeAgentNotes, getSeoHostPatterns, getSeoSiteUrl, runtimeConfig } from './runtimeConfig';
import { getAgentSlugFromPath } from './agentRouting';

export interface SeoAdapter {
  id: string;
  name: string;
  description?: string;
  notes?: string;
}

const META_DESCRIPTION_SELECTOR = 'meta[name="description"]';
const META_OG_TITLE_SELECTOR = 'meta[property="og:title"]';
const META_OG_DESCRIPTION_SELECTOR = 'meta[property="og:description"]';
const META_OG_TYPE_SELECTOR = 'meta[property="og:type"]';
const CANONICAL_SELECTOR = 'link[rel="canonical"]';

export function slugifySeoValue(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function stripMarkdownForSeo(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/[*_~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function getSeoDescription(description?: string, notes?: string): string {
  const fromDescription = description?.trim();
  if (fromDescription) {
    return fromDescription;
  }
  if (!notes) {
    return getApplicationDescription();
  }
  const text = stripMarkdownForSeo(notes);
  return text.length > 160 ? `${text.slice(0, 157).trimEnd()}...` : text;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeSiteOrigin(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  try {
    return new URL(trimmed).origin;
  } catch {
    return null;
  }
}

function wildcardPatternToRegex(pattern: string): RegExp | null {
  const trimmed = pattern.trim();
  if (!trimmed) {
    return null;
  }

  const regexSource = `^${escapeRegex(trimmed).replace(/\\\*/g, '.*')}$`;
  try {
    return new RegExp(regexSource, 'i');
  } catch {
    return null;
  }
}

function isAllowedCurrentOrigin(currentOrigin: string): boolean {
  const configuredOrigins = [getSeoSiteUrl(), ...getSeoAlternateSiteUrls()]
    .map(normalizeSiteOrigin)
    .filter((value): value is string => Boolean(value));

  if (configuredOrigins.includes(currentOrigin)) {
    return true;
  }

  return getSeoHostPatterns().some((pattern) => {
    const regex = wildcardPatternToRegex(pattern);
    return regex ? regex.test(currentOrigin) : false;
  });
}

export function getRuntimeSeoAdapterById(adapterId?: string | null): SeoAdapter | null {
  const normalizedId = adapterId?.trim();
  if (!normalizedId) {
    return null;
  }

  const match = runtimeConfig.adapters.find((adapter) => adapter?.id?.trim() === normalizedId);
  if (!match) {
    return null;
  }

  return {
    id: match.id,
    name: match.name?.trim() || match.id,
    description: match.description?.trim() || undefined,
    notes: match.notes?.trim() || undefined,
  };
}

export function getRuntimeSeoAdapterBySlug(pathname?: string): SeoAdapter | null {
  if (typeof window === 'undefined' && !pathname) {
    return null;
  }

  const slug = getAgentSlugFromPath(pathname || window.location.pathname);
  if (!slug) {
    return null;
  }

  const match = runtimeConfig.adapters.find((adapter) => {
    const adapterNameSlug = slugifySeoValue(adapter.name || '');
    const adapterIdSlug = slugifySeoValue(adapter.id || '');
    return slug === adapterNameSlug || slug === adapterIdSlug;
  });

  if (!match) {
    return null;
  }

  return {
    id: match.id,
    name: match.name?.trim() || match.id,
    description: match.description?.trim() || undefined,
    notes: match.notes?.trim() || undefined,
  };
}

function ensureMetaTag(selector: string, attributeName: string, attributeValue: string): HTMLMetaElement | null {
  if (typeof document === 'undefined') {
    return null;
  }
  const existing = document.querySelector<HTMLMetaElement>(selector);
  if (existing) {
    return existing;
  }
  const meta = document.createElement('meta');
  meta.setAttribute(attributeName, attributeValue);
  document.head.appendChild(meta);
  return meta;
}

function ensureCanonicalTag(): HTMLLinkElement | null {
  if (typeof document === 'undefined') {
    return null;
  }
  const existing = document.querySelector<HTMLLinkElement>(CANONICAL_SELECTOR);
  if (existing) {
    return existing;
  }
  const link = document.createElement('link');
  link.rel = 'canonical';
  document.head.appendChild(link);
  return link;
}

export function applyDocumentSeo(adapter: SeoAdapter | null): void {
  if (typeof document === 'undefined') {
    return;
  }

  const appName = getApplicationName();
  const title = adapter ? `${adapter.name} | ${appName}` : appName;
  const description = adapter
    ? getSeoDescription(adapter.description, adapter.notes)
    : getApplicationDescription();

  document.title = title;

  const descriptionTag = ensureMetaTag(META_DESCRIPTION_SELECTOR, 'name', 'description');
  if (descriptionTag) {
    descriptionTag.content = description;
  }

  const ogTitleTag = ensureMetaTag(META_OG_TITLE_SELECTOR, 'property', 'og:title');
  if (ogTitleTag) {
    ogTitleTag.content = title;
  }

  const ogDescriptionTag = ensureMetaTag(META_OG_DESCRIPTION_SELECTOR, 'property', 'og:description');
  if (ogDescriptionTag) {
    ogDescriptionTag.content = description;
  }

  const ogTypeTag = ensureMetaTag(META_OG_TYPE_SELECTOR, 'property', 'og:type');
  if (ogTypeTag) {
    ogTypeTag.content = 'website';
  }

  const canonicalTag = ensureCanonicalTag();
  if (canonicalTag && typeof window !== 'undefined') {
    const configuredSiteUrl = getSeoSiteUrl();
    const currentOrigin = window.location.origin;
    const baseOrigin = configuredSiteUrl
      ? new URL(configuredSiteUrl.endsWith('/') ? configuredSiteUrl : `${configuredSiteUrl}/`).origin
      : '';
    const effectiveOrigin = currentOrigin && isAllowedCurrentOrigin(currentOrigin)
      ? currentOrigin
      : baseOrigin || currentOrigin;
    const canonicalUrl = `${effectiveOrigin}${window.location.pathname}`;
    canonicalTag.href = canonicalUrl;
  }
}

export function shouldRenderAgentNotesForSeo(): boolean {
  return getSeoExposeAgentNotes();
}
