import { RefObject, useEffect } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'button:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

interface UseFocusTrapOptions {
  enabled: boolean;
  onEscape?: () => void;
}

export function useFocusTrap<T extends HTMLElement>(
  containerRef: RefObject<T | null>,
  { enabled, onEscape }: UseFocusTrapOptions
) {
  useEffect(() => {
    if (!enabled || !containerRef.current) {
      return;
    }

    const container = containerRef.current;
    const previousActiveElement = document.activeElement as HTMLElement | null;
    const focusableElements = Array.from(
      container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    ).filter((el) => !el.hasAttribute('disabled') && el.tabIndex !== -1);

    const first = focusableElements[0] || container;
    const last = focusableElements[focusableElements.length - 1] || container;
    first.focus({ preventScroll: true });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onEscape?.();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      if (focusableElements.length === 0) {
        event.preventDefault();
        container.focus({ preventScroll: true });
        return;
      }

      const active = document.activeElement as HTMLElement | null;
      if (event.shiftKey) {
        if (!active || active === first || !container.contains(active)) {
          event.preventDefault();
          last.focus({ preventScroll: true });
        }
        return;
      }

      if (!active || active === last || !container.contains(active)) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previousActiveElement?.focus?.({ preventScroll: true });
    };
  }, [enabled, onEscape, containerRef]);
}
