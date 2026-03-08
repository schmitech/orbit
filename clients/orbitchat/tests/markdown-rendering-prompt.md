# Markdown Renderer Prompt (GPT-5.4)

You are generating a Markdown-only rendering test artifact for `src/components/markdown/MarkdownRenderer.tsx`.

Hard constraints:
- Output ONLY Markdown.
- No prose outside headings, lists, blockquotes, tables, and code fences.
- Do not use placeholders like "...".
- Include at least 30 sections.
- Include at least 20 tables total.
- Include at least 12 fenced code blocks across multiple languages.

Create sections in this exact order:

# Core Markdown Coverage
Include examples for:
1. Headings `#` through `######`.
2. Paragraphs with soft wraps and hard line breaks.
3. Emphasis: italic, bold, bold-italic, strikethrough.
4. Inline code and fenced code blocks.
5. Ordered, unordered, and mixed lists.
6. Task lists with checked/unchecked items.
7. Nested blockquotes (single and multi-level).
8. Horizontal rules.
9. Escaped markdown characters.
10. Inline links and bare URL links.
11. Image markdown (use placeholder URLs).

# Table Coverage (High Priority)
Include at least 20 tables covering:
1. Basic GFM table.
2. Alignment variants (left/center/right).
3. Wide tables with many columns.
4. Tables with long cell content and wrapped text.
5. Tables containing inline code, links, emphasis, and math.
6. Tables with empty cells.
7. Tables with numeric/date/text mixed values.
8. Tables following a sentence on previous line.
9. Multiple consecutive tables.
10. A table that appears after a list item.

Table validity rules (must follow for every table):
- Keep each table row on exactly one line (no wrapped/split cells across lines).
- Ensure header, separator, and every data row have the same number of columns.
- Use a valid separator row with only hyphens/colons/pipes (e.g., `|:---|:---:|---:|`).
- Do not add extra trailing pipes that create empty phantom columns.
- Include a blank line before and after each table unless it is directly following a list item test case.

# Code Block Coverage
Include fenced blocks for at least these languages:
- `js`, `ts`, `tsx`, `json`, `yaml`, `bash`, `python`, `sql`, `html`, `css`, `markdown`, `text`

Also include:
1. One code block without language tag.
2. One very long line to test horizontal overflow.
3. One block with many lines (50+).
4. One block containing backticks inside strings.

# Rich Markdown + Feature Integrations
Include valid examples for:
1. Mermaid blocks (multiple diagram types).
2. Chart blocks (`chart`, `chart-json`, `chart-table`).
3. SVG block.
4. ABC/music block.
5. Math inline `$...$` and display `\[...\]`.
6. Currency values near math to test delimiter handling (`$5`, `$1,200`, `$x$).
7. LaTeX environments (`\\begin{aligned}...\\end{aligned}`).

# Link Rendering Cases
Include:
1. Inline text links.
2. Bare URL where link text equals URL.
3. Bare URL with path/query/hash.
4. Multiple links in one paragraph.
5. Mixed http/https/mailto links.

# Real-World Document Scenarios
Include full mini-doc examples for:
1. Release notes.
2. Incident postmortem.
3. API docs snippet.
4. Tutorial with steps + code + table.
5. FAQ style section.

# Edge Cases
Include valid but tricky markdown:
1. Adjacent emphasis markers.
2. Backslash escapes in text and math.
3. Mixed RTL/LTR text sample.
4. Unicode/emoji in headings and table cells.
5. Deeply nested lists (up to 4 levels).
6. Blockquote containing list + table + code.
7. Consecutive fenced blocks of different languages.

# Invalid / Fallback Cases
Include exactly 12 intentionally malformed or ambiguous markdown snippets to test graceful fallback:
1. Broken table separator rows.
2. Unclosed code fence.
3. Mismatched emphasis markers.
4. Malformed link syntax.
5. Broken image syntax.
6. Bad math delimiters (`$a = $b$ + c$`).
7. Unbalanced LaTeX braces.
8. Incomplete mermaid block.
9. Invalid chart JSON block.
10. Invalid HTML fragment mixed with markdown.
11. Dangling list markers.
12. Invalid blockquote markers.

Final check before output:
- Ensure output is only Markdown test content.
- Ensure strong coverage for tables and mixed-content blocks.
- Ensure both valid and invalid cases are present.

---

# Markdown Renderer Prompt (Short Mode)

You are generating a compact Markdown-only renderer test sheet.

Hard constraints:
- Output ONLY Markdown.
- No explanations.
- Produce exactly 12 sections.
- Include exactly 5 tables, 4 code blocks, and 3 invalid snippets.

Required coverage in short mode:
1. Headings, paragraph text, emphasis, lists, blockquote.
2. One task list.
3. One basic table, one aligned table, one wide table, one mixed-content table, one sparse table.
4. Code fences in `ts`, `json`, `bash`, and one no-language block.
5. One Mermaid block.
6. One Chart block.
7. One inline and one display math sample.
8. One bare URL link and one normal markdown link.
9. Three invalid snippets:
   - unclosed code fence
   - malformed table
   - malformed math delimiters

Short mode table validity rules:
- Keep each row on one line only.
- Maintain identical column count for header/separator/data rows.
- Use a syntactically valid separator row.

Final check:
- exactly 12 sections
- exactly 5 tables
- exactly 4 code blocks
- exactly 3 invalid snippets
- output only Markdown
