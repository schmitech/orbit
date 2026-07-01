# Adding a new language

OrbitChat's UI chrome (buttons, labels, tooltips, messages) is translated via
[react-i18next](https://react.i18next.com/). Translation bundles are statically
imported JSON files — there's no build step or code generation, so adding a
language is a content task, not a code change.

This does **not** cover admin-authored content (`application.name`,
`application.description`, `inputPlaceholder`, adapter names/descriptions,
header/footer text) — those are written directly in `orbitchat.yaml` in
whatever language the admin wants, and are out of scope for this guide.

## Steps to add a language (example: German, `de`)

### 1. Add the language to the supported-languages list

`src/utils/languages.ts`:

```ts
export const SUPPORTED_LANGUAGES = ['en', 'fr', 'de'] as const;

export const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  en: 'English',
  fr: 'Français',
  de: 'Deutsch', // add the language's own name, in its own language
};
```

`LANGUAGE_LABELS` values are **not** run through `t()` — a language names
itself in the Settings switcher, which is standard i18n UX (don't translate
"Deutsch" into "German" when displayed to a German speaker).

### 2. Create the translation bundle

Copy `src/locales/en.json` to `src/locales/de.json` and translate every value.
Keep the JSON structure and key names **identical** to `en.json` — only the
values change. Do not add, remove, or rename keys in the new file; that's
handled in step 4 below if you're also adding new strings elsewhere.

```bash
cp src/locales/en.json src/locales/de.json
# then translate de.json's values
```

Watch for:
- **Interpolation placeholders** like `{{count}}`, `{{title}}`, `{{filename}}` —
  keep them verbatim in the translated string; only reorder/rephrase the
  surrounding text if the target language's grammar requires it.
- **Plural keys** — some keys use i18next's plural suffixes, e.g.
  `sidebar.results_one` / `sidebar.results_other`. i18next picks the right
  form automatically based on the `count` value passed to `t()`. Some
  languages (Arabic, Russian, Polish, etc.) have more than two plural forms —
  i18next supports `_zero`, `_two`, `_few`, `_many` suffixes per
  [CLDR plural rules](https://www.i18next.com/translation-function/plurals);
  add whichever forms the target language needs instead of just `_one`/`_other`.

### 3. Register the bundle in `src/i18n.ts`

```ts
import en from './locales/en.json';
import fr from './locales/fr.json';
import de from './locales/de.json';

const resources = {
  en: { translation: en },
  fr: { translation: fr },
  de: { translation: de },
};
```

### 4. Verify key parity

Before committing, confirm the new bundle has exactly the same keys as
`en.json` (nothing missing, nothing extra):

```bash
node -e "
const en = require('./src/locales/en.json');
const de = require('./src/locales/de.json');
function keys(obj, prefix='') {
  let out = [];
  for (const k in obj) {
    const path = prefix ? prefix+'.'+k : k;
    if (typeof obj[k] === 'object' && obj[k] !== null) out = out.concat(keys(obj[k], path));
    else out.push(path);
  }
  return out;
}
const enKeys = keys(en).sort();
const deKeys = keys(de).sort();
console.log('missing in de:', enKeys.filter(k => !deKeys.includes(k)));
console.log('extra in de:', deKeys.filter(k => !enKeys.includes(k)));
"
```

Both arrays should print empty.

### 5. Enable it in config

Add the new language code to `i18n.activeLanguages` in `orbitchat.yaml` (and
in `orbitchat.yaml.example` if you want it documented as an example):

```yaml
i18n:
  activeLanguages: ["en", "fr", "de"]
  defaultLanguage: "en"
```

Only languages listed here appear in the Settings > Language switcher. A
language can be present in the bundle but not listed here (e.g. to stage a
translation before announcing it) — that's harmless, it just stays hidden.

### 6. Build and test

```bash
npm run build   # tsc + vite build — confirms the JSON imports resolve
npm run lint    # zero-warnings check
npm run dev     # then: Settings > Language > select the new language,
                # confirm UI text swaps immediately, reload to confirm it
                # persists (localStorage key: orbit-chat-language)
```

## Adding a brand-new UI string later

If a future feature adds new UI text, add the key + English value to
`en.json` first, then add the same key with translated values to every other
language bundle (`fr.json`, `de.json`, etc.) — all bundles must always have
matching key sets. Use the key-parity check in step 4 to catch drift.

## Files touched by this process

| File | What changes |
|---|---|
| `src/utils/languages.ts` | Add language code + its own-language display name |
| `src/locales/<lang>.json` | New file: full translated bundle |
| `src/i18n.ts` | Import and register the new bundle |
| `orbitchat.yaml` (and `.example`) | Add the code to `i18n.activeLanguages` |
