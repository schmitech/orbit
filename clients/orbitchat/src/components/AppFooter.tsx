import {
  getEnableFooter,
  getFooterText,
  getFooterBgColor,
  getFooterTextColor,
  getFooterShowBorder,
  getFooterLayout,
  getFooterAlign,
  getFooterTopPadding,
  getFooterNavLinks,
} from '../utils/runtimeConfig';

export function AppFooter() {
  if (!getEnableFooter()) return null;

  const text = getFooterText();
  const bgColor = getFooterBgColor();
  const textColor = getFooterTextColor();
  const showBorder = getFooterShowBorder();
  const layout = getFooterLayout();
  const align = getFooterAlign();
  const topPadding = getFooterTopPadding();
  const navLinks = getFooterNavLinks();
  const borderClass = showBorder ? 'border-t border-slate-200/80 dark:border-[#333645]' : '';
  const paddingClass = topPadding === 'normal' ? 'pt-3 pb-3' : 'pt-5 pb-3';
  const containerClass =
    layout === 'inline'
      ? `flex w-full flex-col gap-1 sm:flex-row sm:items-center ${align === 'center' ? 'items-center justify-center text-center' : 'items-start justify-between text-left'}`
      : align === 'center'
      ? 'flex w-full flex-col items-center justify-center gap-1 text-center'
      : 'flex w-full flex-col items-start justify-center gap-1 text-left';
  const linksJustifyClass = align === 'center' ? 'justify-center' : 'justify-start';
  const linkBaseClass =
    'inline-flex min-h-10 items-center rounded-md px-2.5 text-xs font-medium transition-colors hover:bg-slate-100 hover:text-blue-700 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-[#2b2d39] dark:hover:text-blue-300 sm:text-sm';

  return (
    <footer
      className={`shrink-0 bg-transparent px-4 text-sm ${paddingClass} ${borderClass}`.trim()}
      style={{
        backgroundColor: bgColor || undefined,
        color: textColor || undefined,
      }}
    >
      <div className={containerClass}>
        {text && (
          <p className="text-xs text-slate-700 dark:text-slate-200">{text}</p>
        )}
        {navLinks.length > 0 && (
          <nav aria-label="Footer links">
            <ul className={`flex flex-wrap items-center ${linksJustifyClass} gap-1.5 sm:gap-2`}>
              {navLinks.map((link, index) => {
                const showInlineSeparator = layout === 'inline' && index > 0;
                return (
                  <li key={link.url} className="flex items-center">
                    {showInlineSeparator && (
                      <span className="mr-1.5 text-slate-400 dark:text-slate-500" aria-hidden="true">
                        ·
                      </span>
                    )}
                    <a
                      href={link.url}
                      className={linkBaseClass}
                      style={{ color: textColor || undefined }}
                    >
                      {link.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </div>
    </footer>
  );
}
