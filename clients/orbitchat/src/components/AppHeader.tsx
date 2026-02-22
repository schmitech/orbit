import {
  getEnableHeader,
  getHeaderLogoUrl,
  getHeaderLogoUrlLight,
  getHeaderLogoUrlDark,
  getHeaderBrandName,
  getHeaderBgColor,
  getHeaderTextColor,
  getHeaderShowBorder,
  getHeaderNavLinks,
} from '../utils/runtimeConfig';
import { AuthStatus } from './AuthStatus';
import { useTheme } from '../contexts/ThemeContext';
import { useEffect, useRef } from 'react';

export function AppHeader() {
  const { isDark } = useTheme();
  const warnedMissingLogoRef = useRef(false);

  const logoUrlDefault = getHeaderLogoUrl();
  const logoUrlLight = getHeaderLogoUrlLight();
  const logoUrlDark = getHeaderLogoUrlDark();
  const logoUrl = isDark
    ? (logoUrlDark || logoUrlDefault || logoUrlLight)
    : (logoUrlLight || logoUrlDefault || logoUrlDark);
  const brandName = getHeaderBrandName();
  const bgColor = getHeaderBgColor();
  const textColor = getHeaderTextColor();
  const showBorder = getHeaderShowBorder();
  const navLinks = getHeaderNavLinks();
  const headerBorderClass = showBorder ? 'border-b border-slate-200/80 dark:border-[#333645]' : '';
  const navLinkBaseClass =
    'inline-flex min-h-10 items-center rounded-md px-2.5 text-sm font-medium transition-colors hover:bg-slate-100 hover:text-blue-700 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-[#2b2d39] dark:hover:text-blue-300';

  useEffect(() => {
    if (warnedMissingLogoRef.current) return;
    if (logoUrlDefault || logoUrlLight || logoUrlDark) return;
    warnedMissingLogoRef.current = true;
    console.warn('[AppHeader] Header is enabled but no logo is configured. Set header.logoUrl, header.logoUrlLight, or header.logoUrlDark in orbitchat.yaml.');
  }, [logoUrlDark, logoUrlDefault, logoUrlLight]);

  if (!getEnableHeader()) return null;

  return (
    <header
      className={`sticky top-0 z-30 shrink-0 bg-transparent px-3 pt-4 pb-2 sm:px-6 sm:pt-5 sm:pb-3 ${headerBorderClass}`.trim()}
      style={{
        backgroundColor: bgColor || undefined,
        color: textColor || undefined,
      }}
    >
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-2 sm:gap-3">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {logoUrl && (
            <img src={logoUrl} alt={brandName || 'Logo'} className="h-8 w-auto flex-shrink-0 sm:h-10" />
          )}
          {brandName && (
            <span className="truncate text-sm font-semibold tracking-[0.01em] sm:text-lg">{brandName}</span>
          )}
        </div>
        <div className="flex min-w-0 items-center justify-end gap-2 sm:gap-4">
          {navLinks.length > 0 && (
            <nav aria-label="Header links" className="hidden sm:block">
              <ul className="flex items-center gap-1.5 sm:gap-2">
                {navLinks.map((link) => (
                  <li key={link.url}>
                    <a
                      href={link.url}
                      className={navLinkBaseClass}
                      style={{ color: textColor || undefined }}
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}
          <AuthStatus />
        </div>
      </div>
    </header>
  );
}
