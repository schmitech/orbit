import {
  getEnableHeader,
  getHeaderLogoUrl,
  getHeaderLogoUrlLight,
  getHeaderLogoUrlDark,
  getHeaderLogoHeight,
  getHeaderLogoWidth,
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
  const logoHeight = getHeaderLogoHeight();
  const logoWidth = getHeaderLogoWidth();
  const hasCustomLogoDimensions = !!(logoHeight || logoWidth);
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
      className={`relative z-30 shrink-0 bg-white dark:bg-[#212121] px-3 pt-2 pb-1 sm:px-6 sm:pt-3 sm:pb-2 md:pt-5 md:sticky md:top-0 ${headerBorderClass}`.trim()}
      style={{
        backgroundColor: bgColor || undefined,
        color: textColor || undefined,
      }}
    >
      <div className="mx-auto flex w-full max-w-7xl items-center justify-center md:justify-between gap-2 px-4 sm:gap-3 sm:px-0">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {logoUrl && (
            <a
              href="/"
              aria-label="Go to home page"
              className="inline-flex items-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-blue-300 dark:focus-visible:ring-offset-[#212121]"
            >
              <img
                src={logoUrl}
                alt="Logo"
                draggable={false}
                className={`block flex-shrink-0 select-none ${hasCustomLogoDimensions ? '' : 'h-8 w-auto sm:h-10'}`.trim()}
                style={{
                  WebkitUserDrag: 'none',
                  ...(logoHeight ? { height: logoHeight } : {}),
                  ...(logoWidth ? { width: logoWidth } : {}),
                }}
              />
            </a>
          )}
        </div>
        <div className="hidden md:flex min-w-0 items-center justify-end gap-2 sm:gap-4">
          {navLinks.length > 0 && (
            <nav aria-label="Header links" className="hidden sm:block">
              <ul className="flex items-center gap-1.5 sm:gap-2">
                {navLinks.map((link) => (
                  <li key={link.url}>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
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
