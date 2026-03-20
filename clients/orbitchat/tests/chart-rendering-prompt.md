# Chart Rendering Test Prompt

Generate a Markdown-only test sheet for a chart renderer. Follow every rule exactly.

## Rules

1. Output ONLY Markdown. No explanations, no prose outside headings and code fences.
2. Every chart must be inside a fenced code block with one of these languages: `chart`, `chart-json`, or `chart-table`.
3. Produce exactly 30 chart blocks. Every block must be valid and renderable.
4. Do not use placeholders like "..." — all data must be complete.
5. Use realistic business-like numbers (not trivial 1, 2, 3).

## Syntax Reference

There are three input formats. Study these examples carefully and follow the exact syntax.

**Format A — key/value with simple data:**

```
type: bar
title: Sales by Quarter
data: [45000, 52000, 48000, 60000]
labels: [Q1, Q2, Q3, Q4]
```

Language tag: `chart`

**Format B — key/value with markdown table:**

```
type: line
title: Revenue vs Expenses
showLegend: true
| Month | Revenue | Expenses |
|-------|---------|----------|
| Jan   | 100000  | 80000    |
| Feb   | 112000  | 85000    |
```

Language tag: `chart` or `chart-table`

**Format C — key/value with JSON data and series:**

```
type: composed
title: Revenue and Margin
xKey: month
yAxisLabel: Revenue
yAxisRightLabel: Margin
showLegend: true
data: [{"month":"Jan","revenue":120000,"margin":0.28},{"month":"Feb","revenue":134000,"margin":0.31}]
series: [{"key":"revenue","name":"Revenue","type":"bar","color":"#3b82f6","yAxisId":"left"},{"key":"margin","name":"Margin","type":"line","color":"#f59e0b","yAxisId":"right"}]
```

Language tag: `chart`

**Format D — full JSON object:**

```json
{
  "type": "pie",
  "title": "Traffic Sources",
  "xKey": "source",
  "showLegend": true,
  "data": [
    { "source": "Organic", "value": 42 },
    { "source": "Paid", "value": 28 }
  ],
  "series": [{ "key": "value", "name": "Share" }]
}
```

Language tag: `chart-json`

**Format E — numeric x-axis with calendar years (time series):**

Use `xAxisType: number` when the x-values are years **stored as numbers** (not strings like `"2017"`). The client renders year ticks **without** a thousands separator (`2017`, `2023`), while ordinary large counts on the y-axis still use grouping (`50,000`) when applicable.

```
type: line
title: Reported incidents by year
xKey: Year
xAxisType: number
xAxisLabel: Year
yAxisLabel: Incidents
showGrid: true
| Year | Incidents |
|------|-----------|
| 2017 | 45230     |
| 2018 | 46810     |
| 2019 | 48190     |
| 2020 | 49340     |
| 2021 | 50120     |
```

Language tag: `chart` or `chart-table`

Equivalent `chart-json` (strict JSON — note numeric `year` values):

```json
{
  "type": "line",
  "title": "Reported incidents by year",
  "xKey": "year",
  "xAxisType": "number",
  "xAxisLabel": "Year",
  "yAxisLabel": "Incidents",
  "showGrid": true,
  "data": [
    { "year": 2017, "incidents": 45230 },
    { "year": 2018, "incidents": 46810 },
    { "year": 2019, "incidents": 48190 },
    { "year": 2020, "incidents": 49340 },
    { "year": 2021, "incidents": 50120 }
  ],
  "series": [{ "key": "incidents", "name": "Incidents" }]
}
```

Language tag: `chart-json`

## Series Object — IMPORTANT

Every object in a `series` array must use `"key"` for the data field name. Never use `"dataKey"`. This is required.

Complete list of series properties:
- `"key"` — REQUIRED. Must match a field name in the data objects.
- `"name"` — display label for legend.
- `"type"` — `"bar"`, `"line"`, `"area"`, or `"scatter"`. Only needed in composed charts.
- `"color"` — hex color code, e.g. `"#3b82f6"`.
- `"yAxisId"` — `"left"` (default) or `"right"`.
- `"stackId"` — string to group stacked bars/areas.
- `"strokeWidth"` — number, line thickness.
- `"dot"` — `true` or `false`, show data point dots.
- `"opacity"` — number 0 to 1, fill opacity.

## Config Options

One per line in `key: value` format:
- `type` — REQUIRED. One of: `bar`, `line`, `pie`, `area`, `scatter`, `composed`.
- `title`, `description` — chart title and subtitle.
- `xKey` — field name for x-axis values.
- `xAxisLabel`, `yAxisLabel`, `yAxisRightLabel` — axis labels.
- `xAxisType` — `category` (default) or `number`. Use `number` for numeric x-scales (e.g. years as integers — see Format E); year axis ticks render as `2017`, not `2,017`.
- `stacked` — `true` or `false`.
- `showLegend` — `true` or `false`.
- `showGrid` — `true` or `false`.
- `height`, `width` — numbers in pixels.
- `valueFormat` — `number`, `compact`, `currency`, or `percent`.
- `valuePrefix`, `valueSuffix` — strings to prepend/append to values.
- `valueDecimals` — number of decimal places.
- `valueCurrency` — currency code (e.g. `USD`), used with `valueFormat: currency`.
- `colors` — comma-separated hex codes for the color palette.
- `referenceLines` — JSON array, e.g. `[{"y":500,"label":"Target","color":"#ef4444"}]`

## Formatter Object (chart-json only)

In `chart-json` format, `formatter` must be an object (not a string):
```json
"formatter": { "format": "currency", "currency": "USD", "decimals": 0 }
```

---

# Blocks to Generate

## Section 1 — Chart Types (6 blocks, one per type)

1. `bar` — `chart-table` format. 4 categories, single series. `showGrid: true`.
2. `line` — `chart` key/value with inline JSON `data:` and `series:`. 5+ points. Series has `"strokeWidth": 2, "dot": true`.
3. `pie` — `chart-json`. 4–5 slices. Include `showLegend`, `height`, `width`.
4. `area` — `chart-table` format. 6 data points, single series. Include `xAxisLabel` and `yAxisLabel`.
5. `scatter` — `chart` key/value with inline JSON `data:` and `series:`. `xAxisType: number`. 5+ points. Include axis labels.
6. `composed` — `chart-json`. 3+ series mixing bar, line, and area. Dual y-axes. `showLegend: true`, `showGrid: true`.

## Section 2 — Formatter Coverage (4 blocks)

7. `currency` — bar chart, `chart` format. `valueFormat: currency`, `valueCurrency: USD`, `valueDecimals: 0`. Values in thousands.
8. `percent` — area chart, `chart-table` format. Values between 0 and 1. `valueFormat: percent`, `valueDecimals: 1`.
9. `compact` — line chart, `chart` format with inline JSON data. Large values in millions. `valueFormat: compact`.
10. `number` with prefix/suffix — bar chart, `chart-table` format. `valuePrefix: $`, `valueSuffix: M`, `valueDecimals: 2`.

## Section 3 — Series & Axis Features (5 blocks)

11. **Stacked bar** — `chart` format. 3 series each with `"stackId": "stack"` and a custom `"color"`. `stacked: true`, `showLegend: true`.
12. **Dual Y-axis line** — `chart` format. 2 series: one `"yAxisId": "left"`, one `"yAxisId": "right"`. Include `yAxisLabel` and `yAxisRightLabel`.
13. **Multi-series area** — `chart-table` format. 2 area series. Use `series:` to set different `"opacity"` values (0.3 and 0.6).
14. **Line with strokeWidth/dot** — `chart-json`. 2 series: one `"strokeWidth": 3, "dot": true`, another `"strokeWidth": 1, "dot": false`.
15. **Composed with scatter** — `chart-json`. Composed chart mixing bar + scatter series. `showGrid: true`.

## Section 4 — Reference Lines (2 blocks)

16. **Y reference line** — bar chart. `referenceLines: [{"y": 500, "label": "Target", "color": "#ef4444", "strokeDasharray": "4 4", "position": "end"}]`.
17. **X and Y reference lines** — line chart. Two reference lines: one at an `x` category value (`"position": "start"`), one at a `y` value (`"position": "middle"`). Different colors.

## Section 5 — Input Format Variants (4 blocks)

18. **Numeric array + labels** — `chart` format. `data: [45, 62, 38, 71]` with `labels: [Q1, Q2, Q3, Q4]`. Pie chart.
19. **chart-table with config above** — `chart-table`. Bar chart with `type`, `title`, `xKey`, `showLegend` lines above the markdown table.
20. **Full chart-json** — `chart-json`. Area chart. JSON object with: `type`, `title`, `description`, `data`, `series` (using `"key"`), `xKey`, `xAxisLabel`, `yAxisLabel`, `formatter` (as `{"format":"number","decimals":1}`), `showLegend`, `showGrid`, `height`.
21. **Key/value with JSON arrays** — `chart` format. Composed chart. Config lines for `type`, `title`, `xKey`, then `data:` and `series:` as inline JSON.

## Section 6 — Data Scenarios (5 blocks)

22. **Full month names** — line chart. Use "January", "February", etc. through June as x-values. The renderer abbreviates them automatically.
23. **Negative and zero values** — bar chart. Mix of positive, negative, and zero values. Include `referenceLines: [{"y": 0, "label": "Break-even", "color": "#9ca3af"}]`.
24. **Sparse data** — `chart-json` bar chart. Some data objects are missing fields that others have. 2 series. Renderer handles gaps.
25. **Large dataset (24 rows)** — area chart. 24 data points (e.g. hourly readings over a day). `xAxisType: number`.
26. **Unicode labels** — `chart-json` bar chart. Labels: "São Paulo", "München", "東京", "Москва".

## Section 7 — Edge Cases (4 blocks)

27. **Mixed x-value types** — `chart-json` bar chart. X-values mix numbers and strings: `1`, `"2A"`, `3`, `"4B"`.
28. **Long labels** — line chart. X-labels 20+ characters each (e.g. "Customer Acquisition Cost"). 5 points.
29. **Single data point** — bar chart with exactly 1 row/value.
30. **Duplicate categories** — `chart-table` bar chart. Same category label appears multiple times (e.g. "North" twice, "South" twice).

---

# Final Checks

Before outputting, verify:
- Exactly 30 fenced code blocks.
- Every `series` object uses `"key"` — never `"dataKey"`.
- In `chart-json` blocks, `formatter` is an object like `{"format":"currency","decimals":0}`, never a bare string.
- All three language tags (`chart`, `chart-json`, `chart-table`) are used.
- All six chart types (`bar`, `line`, `pie`, `area`, `scatter`, `composed`) appear at least twice.
- Data values are realistic business numbers.
- Output contains only Markdown — no prose or explanations.
