import { useState, useEffect, useCallback, useRef } from 'react';
import { getEnableAutocomplete, getEnableApiMiddleware, resolveApiUrl } from '../utils/runtimeConfig';
import { debugLog, debugWarn } from '../utils/debug';

const DEBOUNCE_DELAY = 300;  // 300ms debounce
const MIN_QUERY_LENGTH = 3;
const MAX_SUGGESTIONS = 5;

export interface AutocompleteSuggestion {
  text: string;
}

export interface UseAutocompleteOptions {
  enabled?: boolean;
  apiKey?: string | null;
  apiUrl?: string | null;
  adapterName?: string | null;
  useMiddleware?: boolean;
}

export interface UseAutocompleteResult {
  suggestions: AutocompleteSuggestion[];
  isLoading: boolean;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrevious: () => void;
  clearSuggestions: () => void;
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
    apiKey,
    apiUrl,
    adapterName,
    useMiddleware = getEnableApiMiddleware()
  } = options;

  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const abortControllerRef = useRef<AbortController>();

  const fetchSuggestions = useCallback(async (searchQuery: string) => {
    if (!enabled || searchQuery.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      return;
    }

    const middlewareEnabled = Boolean(useMiddleware);
    const requiresApiKey = !middlewareEnabled;
    const requiresAdapter = middlewareEnabled;

    if (requiresApiKey && !apiKey) {
      setSuggestions([]);
      return;
    }

    if (requiresAdapter && !adapterName) {
      setSuggestions([]);
      return;
    }

    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setIsLoading(true);

    try {
      const headers: Record<string, string> = {};
      let requestUrl: string;

      if (middlewareEnabled) {
        const params = new URLSearchParams();
        params.set('q', searchQuery);
        params.set('limit', String(MAX_SUGGESTIONS));
        requestUrl = `/api/v1/autocomplete?${params.toString()}`;
        headers['X-Adapter-Name'] = adapterName as string;
      } else {
        const resolvedUrl = resolveApiUrl(apiUrl);
        const url = new URL(`${resolvedUrl}/v1/autocomplete`);
        url.searchParams.set('q', searchQuery);
        url.searchParams.set('limit', String(MAX_SUGGESTIONS));
        requestUrl = url.toString();
        headers['X-API-Key'] = apiKey as string;
      }

      const response = await fetch(requestUrl, {
        method: 'GET',
        headers,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        debugWarn('[useAutocomplete] Request failed:', response.status);
        setSuggestions([]);
        return;
      }

      const data = await response.json();
      setSuggestions(data.suggestions || []);
      setSelectedIndex(-1);

      debugLog('[useAutocomplete] Received', data.suggestions?.length || 0, 'suggestions');
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was cancelled, ignore
        return;
      }
      // Autocomplete failures should not block the user
      debugWarn('[useAutocomplete] Error:', error instanceof Error ? error.message : String(error));
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, [enabled, apiKey, apiUrl, adapterName, useMiddleware]);

  // Debounced effect
  useEffect(() => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    if (!enabled || query.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      return;
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
    setSelectedIndex(-1);
  }, []);

  return {
    suggestions,
    isLoading,
    selectedIndex,
    setSelectedIndex,
    selectNext,
    selectPrevious,
    clearSuggestions
  };
}
