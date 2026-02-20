import {
  getEnableHeader,
  getHeaderLogoUrl,
  getHeaderBrandName,
  getHeaderBgColor,
  getHeaderTextColor,
  getHeaderShowBorder,
  getHeaderNavLinks,
} from '../utils/runtimeConfig';
import { AuthStatus } from './AuthStatus';

export function AppHeader() {
  if (!getEnableHeader()) return null;

  const logoUrl = getHeaderLogoUrl();
  const brandName = getHeaderBrandName();
  const bgColor = getHeaderBgColor();
  const textColor = getHeaderTextColor();
  const showBorder = getHeaderShowBorder();
  const navLinks = getHeaderNavLinks();
  const headerBorderClass = showBorder ? 'border-b border-slate-200/80 dark:border-[#333645]' : '';
  const hasCustomBackground = Boolean(bgColor);
  const navLinkBaseClass =
    'inline-flex min-h-10 items-center rounded-md px-2.5 text-sm font-medium transition-colors hover:bg-slate-100 hover:text-blue-700 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-[#2b2d39] dark:hover:text-blue-300';

  return (
    <header
      className={`sticky top-0 z-30 shrink-0 px-3 py-2.5 sm:px-6 sm:py-3 backdrop-blur-md ${
        hasCustomBackground ? '' : 'bg-white/85 dark:bg-[#212121]/85'
      } ${headerBorderClass}`.trim()}
      style={{
        backgroundColor: bgColor || undefined,
        color: textColor || undefined,
      }}
    >
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {logoUrl && (
            <img src={logoUrl} alt={brandName || 'Logo'} className="h-7 w-auto flex-shrink-0 sm:h-8" />
          )}
          {brandName && (
            <span className="truncate text-base font-semibold tracking-[0.01em] sm:text-lg">{brandName}</span>
          )}
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2 sm:gap-4">
          {navLinks.length > 0 && (
            <nav aria-label="Header links">
              <ul className="flex flex-wrap items-center gap-1.5 sm:gap-2">
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
