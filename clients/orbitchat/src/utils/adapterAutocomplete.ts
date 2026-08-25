export function resolveAutocompleteSupport(adapterInfo: unknown): boolean | null {
  if (!adapterInfo || typeof adapterInfo !== 'object') {
    return null;
  }

  const info = adapterInfo as Record<string, unknown>;
  const directCapabilityKeys = [
    'supportsAutocomplete',
    'isAutocompleteSupported',
    'autocompleteSupported'
  ];

  for (const key of directCapabilityKeys) {
    if (typeof info[key] === 'boolean') {
      return info[key] as boolean;
    }
  }

  const nestedCapabilityParents = ['capabilities', 'features'];
  const nestedCapabilityKeys = ['autocomplete', 'supportsAutocomplete', 'autocomplete_supported'];

  for (const parent of nestedCapabilityParents) {
    const nested = info[parent];
    if (!nested || typeof nested !== 'object') {
      continue;
    }

    const nestedInfo = nested as Record<string, unknown>;
    for (const key of nestedCapabilityKeys) {
      if (typeof nestedInfo[key] === 'boolean') {
        return nestedInfo[key] as boolean;
      }
    }
  }

  return null;
}
