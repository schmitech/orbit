import { useState, useEffect, useCallback, useRef, RefObject } from 'react';
import { getEnableAutocomplete } from '../utils/runtimeConfig';
import { debugLog, debugWarn } from '../utils/debug';

const DEBOUNCE_DELAY = 300;  // 300ms debounce
const MIN_QUERY_LENGTH = 3;
const MAX_SUGGESTIONS = 5;

export interface AutocompleteSuggestion {
  text: string;
}

export interface UseAutocompleteOptions {
  enabled?: boolean;
  apiUrl?: string | null;
  adapterName?: string | null;
  /**
   * Optional ref to refocus after accepting a suggestion (helps on mobile/touch).
   */
  inputRef?: RefObject<HTMLInputElement | HTMLTextAreaElement | null> | null;
}

export interface UseAutocompleteResult {
  suggestions: AutocompleteSuggestion[];
  isLoading: boolean;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrevious: () => void;
  clearSuggestions: () => void;
  /**
   * Re-focus the provided input ref and place the caret at the end of the supplied text.
   */
  focusInputAfterSelection: (appliedText?: string) => void;
  /**
   * Prevents suggestions from refetching until the query changes away from the provided value.
   */
  suppressUntilQueryChange: (query: string) => void;
}

/**
 * Hook for fetching and managing autocomplete suggestions.
 *
 * @param query - The current query text
 * @param options - Configuration options
 * @returns Autocomplete state and controls
 */
export function useAutocomplete(
  query: string,
  options: UseAutocompleteOptions = {}
): UseAutocompleteResult {
  const {
    enabled = getEnableAutocomplete(),
    adapterName,
    inputRef
  } = options;

  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const suppressedQueryRef = useRef<string | null>(null);
  const latestRequestIdRef = useRef(0);
  const suggestionsRef = useRef<AutocompleteSuggestion[]>([]);
  const lastNonEmptySuggestionsRef = useRef<AutocompleteSuggestion[]>([]);

  useEffect(() => {
    suggestionsRef.current = suggestions;
  }, [suggestions]);

  const sanitizeSuggestionText = useCallback((text: unknown): AutocompleteSuggestion | null => {
    if (typeof text !== 'string') {
      return null;
    }
    const normalized = text
      .replace(/[\r\n\u2028\u2029]+/g, ' ')
      .replace(/\s{2,}/g, ' ')
      .trim();

    if (!normalized) {
      return null;
    }

    return { text: normalized };
  }, []);

  const getFallbackSuggestions = useCallback((searchQuery: string): AutocompleteSuggestion[] => {
    const normalizedQuery = searchQuery.toLowerCase().trim();
    const source = lastNonEmptySuggestionsRef.current.length > 0
      ? lastNonEmptySuggestionsRef.current
      : suggestionsRef.current;

    if (!normalizedQuery) {
      return source.slice(0, MAX_SUGGESTIONS);
    }

    const matching = source.filter((suggestion) =>
      suggestion.text.toLowerCase().includes(normalizedQuery)
    );

    if (matching.length > 0) {
      return matching.slice(0, MAX_SUGGESTIONS);
    }

    // Keep the previous visible suggestions to avoid flash-hide during
    // transient empty server responses while the user is still typing.
    return source.slice(0, MAX_SUGGESTIONS);
  }, []);

  const fetchSuggestions = useCallback(async (searchQuery: string) => {
    if (!enabled || searchQuery.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      lastNonEmptySuggestionsRef.current = [];
      return;
    }

    if (!adapterName) {
      setSuggestions([]);
      lastNonEmptySuggestionsRef.current = [];
      return;
    }

    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const requestId = latestRequestIdRef.current + 1;
    latestRequestIdRef.current = requestId;

    setIsLoading(true);

    try {
      const headers: Record<string, string> = {
        'X-Adapter-Name': adapterName
      };

      const params = new URLSearchParams();
      params.set('q', searchQuery);
      params.set('limit', String(MAX_SUGGESTIONS));
      const requestUrl = `/api/v1/autocomplete?${params.toString()}`;

      const response = await fetch(requestUrl, {
        method: 'GET',
        headers,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        debugWarn('[useAutocomplete] Request failed:', response.status);
        setSuggestions(getFallbackSuggestions(searchQuery));
        return;
      }

      const data = await response.json();
      const normalized = Array.isArray(data?.suggestions)
        ? data.suggestions
            .map((suggestion: AutocompleteSuggestion | string | undefined | null) => {
              if (typeof suggestion === 'string') {
                return sanitizeSuggestionText(suggestion);
              }
              return sanitizeSuggestionText(suggestion?.text);
            })
            .filter(
              (value: AutocompleteSuggestion | null): value is AutocompleteSuggestion =>
                value !== null
            )
        : [];

      // Ignore stale responses that return out of order.
      if (requestId !== latestRequestIdRef.current) {
        return;
      }

      // Prevent transient flicker when backend returns no results for a fast-follow query:
      // keep previous relevant suggestions if they still match the current prefix.
      if (normalized.length === 0) {
        setSuggestions(getFallbackSuggestions(searchQuery));
      } else {
        setSuggestions(normalized);
        lastNonEmptySuggestionsRef.current = normalized;
      }
      setSelectedIndex(-1);

      debugLog('[useAutocomplete] Received', normalized.length, 'suggestions');
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was cancelled, ignore
        return;
      }
      // Autocomplete failures should not block the user
      debugWarn('[useAutocomplete] Error:', error instanceof Error ? error.message : String(error));
      setSuggestions(getFallbackSuggestions(searchQuery));
    } finally {
      if (requestId === latestRequestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [enabled, adapterName, sanitizeSuggestionText, getFallbackSuggestions]);

  // Debounced effect
  useEffect(() => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    if (!enabled || query.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      return;
    }

    if (suppressedQueryRef.current) {
      if (query === suppressedQueryRef.current) {
        setSuggestions([]);
        return;
      }
      suppressedQueryRef.current = null;
    }

    debounceTimeoutRef.current = setTimeout(() => {
      fetchSuggestions(query);
    }, DEBOUNCE_DELAY);

    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, [query, fetchSuggestions, enabled]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const selectNext = useCallback(() => {
    setSelectedIndex(prev =>
      prev < suggestions.length - 1 ? prev + 1 : 0
    );
  }, [suggestions.length]);

  const selectPrevious = useCallback(() => {
    setSelectedIndex(prev =>
      prev > 0 ? prev - 1 : suggestions.length - 1
    );
  }, [suggestions.length]);

  const clearSuggestions = useCallback(() => {
    setSuggestions([]);
    lastNonEmptySuggestionsRef.current = [];
    setSelectedIndex(-1);
  }, []);

  const focusInputAfterSelection = useCallback((appliedText?: string) => {
    if (!inputRef?.current) {
      return;
    }

    const run = () => {
      const target = inputRef.current;
      if (!target) {
        return;
      }

      const nextValueLength = typeof appliedText === 'string'
        ? appliedText.length
        : target.value.length;

      target.focus({ preventScroll: true });

      if (typeof target.setSelectionRange === 'function') {
        target.setSelectionRange(nextValueLength, nextValueLength);
      }
    };

    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(run);
    } else {
      setTimeout(run, 0);
    }
  }, [inputRef]);

  const suppressUntilQueryChange = useCallback((query: string) => {
    suppressedQueryRef.current = query;
  }, []);

  return {
    suggestions,
    isLoading,
    selectedIndex,
    setSelectedIndex,
    selectNext,
    selectPrevious,
    clearSuggestions,
    focusInputAfterSelection,
    suppressUntilQueryChange
  };
}
