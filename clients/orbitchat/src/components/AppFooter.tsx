import {
  getEnableFooter,
  getFooterText,
  getFooterBgColor,
  getFooterTextColor,
  getFooterShowBorder,
  getFooterLayout,
  getFooterTopPadding,
  getFooterNavLinks,
} from '../utils/runtimeConfig';

interface AppFooterProps {
  placement?: 'default' | 'sidebar';
  compact?: boolean;
}

export function AppFooter({ placement = 'default', compact = false }: AppFooterProps) {
  if (!getEnableFooter()) return null;

  const text = getFooterText();
  const bgColor = getFooterBgColor();
  const textColor = getFooterTextColor();
  const showBorder = getFooterShowBorder();
  const layout = getFooterLayout();
  const topPadding = getFooterTopPadding();
  const navLinks = getFooterNavLinks();
  const borderClass = showBorder ? 'border-t border-slate-200/80 dark:border-[#333645]' : '';
  const paddingClass = compact
    ? 'pt-2 pb-2'
    : topPadding === 'normal'
      ? 'pt-3 pb-3'
      : 'pt-5 pb-3';
  const containerClass =
    layout === 'inline'
      ? 'flex w-full flex-col gap-1 items-center justify-center text-center sm:flex-row sm:items-center sm:justify-center'
      : 'flex w-full flex-col items-center justify-center gap-1 text-center';
  const linksJustifyClass = 'justify-center';
  const outerRailClass = placement === 'sidebar' ? 'w-full px-2' : 'w-full px-3 sm:px-6';
  const innerRailClass = placement === 'sidebar' ? 'w-full' : 'mx-auto w-full max-w-7xl';
  const linkBaseClass =
    compact
      ? 'inline-flex min-h-7 items-center rounded px-1.5 text-[11px] font-medium transition-colors hover:bg-slate-100 hover:text-blue-700 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-[#2b2d39] dark:hover:text-blue-300'
      : 'inline-flex min-h-10 items-center rounded-md px-2.5 text-xs font-medium transition-colors hover:bg-slate-100 hover:text-blue-700 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-[#2b2d39] dark:hover:text-blue-300 sm:text-sm';

  return (
    <footer
      className={`shrink-0 bg-transparent ${compact ? 'text-xs' : 'text-sm'} ${paddingClass} ${borderClass}`.trim()}
      style={{
        backgroundColor: bgColor || undefined,
        color: textColor || undefined,
      }}
    >
      <div className={outerRailClass}>
        <div className={innerRailClass}>
          <div className={containerClass}>
            {text && (
              <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-slate-700 dark:text-slate-200`}>{text}</p>
            )}
            {navLinks.length > 0 && (
              <nav aria-label="Footer links">
                <ul className={`flex flex-wrap items-center ${linksJustifyClass} ${compact ? 'gap-1' : 'gap-1.5 sm:gap-2'}`}>
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
        </div>
      </div>
    </footer>
  );
}
