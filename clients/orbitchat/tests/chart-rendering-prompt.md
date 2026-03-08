# Chart Rendering Prompt (GPT-5.4)

You are generating a Markdown-only test artifact for a frontend chart parser/renderer.

Hard constraints:
- Output ONLY Markdown.
- No prose outside headings and code fences.
- Every example must be in fenced code blocks using exactly one of:
  - ```chart
  - ```chart-json
  - ```chart-table
- Keep syntax strict and realistic.
- Do not use placeholders like "..."
- Include at least 24 total chart blocks.

Create sections in this exact order:

# Valid Examples
Include working examples that cover:
1. All chart types: `bar`, `line`, `pie`, `area`, `scatter`, `composed`.
2. `chart` key/value config format.
3. `chart-table` format.
4. `chart-json` full object format.
5. Formatter variants: `number`, `compact`, `currency`, `percent`, plus `prefix`, `suffix`, `decimals`.
6. Axis options: `xKey`, `xAxisType` (`category` and `number`), `xAxisLabel`, `yAxisLabel`, `yAxisRightLabel`.
7. Flags/options: `showLegend`, `showGrid`, `stacked`, `height`, `width`.
8. `series` array with mixed series types, custom colors, left/right y-axes, `stackId`, `strokeWidth`, `dot`, `opacity`.
9. `referenceLines` with x and y, labels, color, dash style, position (`start`, `middle`, `end`).
10. One example where `data` is numeric array + `labels`.
11. One example with month names as x-values.
12. One example with negative values and zeros.
13. One example with sparse/missing row fields.
14. One composed chart with 3+ series and dual axes.
15. One large dataset example (20+ rows).

# Edge Cases
Include tricky but valid examples:
- mixed numeric/string x-values
- decimals/large numbers
- duplicated category labels
- unicode labels
- percent + currency formatting mismatch scenarios that are still parseable

# Invalid Examples
Include exactly 10 intentionally broken blocks to trigger parser/error paths:
1. missing `type`
2. empty `data`
3. malformed JSON
4. incomplete table (header only)
5. incomplete row
6. unknown `type`
7. invalid `series` shape
8. invalid `referenceLines` shape
9. mismatched `dataKeys` vs data rows
10. dangling key-value line (`type:` with no value)

Final check before output:
- Ensure all blocks are syntactically diverse.
- Ensure invalid examples are clearly invalid.
- Output only the Markdown test sheet.

---

# Chart Rendering Prompt (Short Mode)

You are generating a compact Markdown-only chart rendering test sheet.

Hard constraints:
- Output ONLY Markdown.
- No explanations.
- Use fenced code blocks with only these languages:
  - ```chart
  - ```chart-json
  - ```chart-table
- Produce exactly 10 blocks total:
  - 7 valid
  - 3 invalid

# Valid Examples
Create 7 valid blocks that collectively cover:
1. `bar` (table format)
2. `line` (key/value + inline JSON data)
3. `pie` (`chart-json`)
4. `scatter` with numeric x-axis (`xAxisType: number`)
5. `composed` with 3+ series and dual y-axes
6. formatter coverage (`currency`, `percent`, `compact`, prefix/suffix/decimals)
7. reference lines (both x and y, labeled)

Also ensure across valid blocks:
- one uses month names
- one includes negative/zero values
- one includes sparse row fields
- one uses `stacked`, `showLegend`, `showGrid`
- one sets `height` and `width`

# Invalid Examples
Create exactly 3 invalid blocks:
1. missing `type`
2. malformed JSON
3. incomplete table (header/separator only)

Final check:
- exactly 10 blocks
- parser-realistic syntax
- no placeholder text
- output only Markdown
