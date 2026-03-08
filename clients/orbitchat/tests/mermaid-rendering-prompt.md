# Mermaid Rendering Prompt (GPT-5.4)

You are generating a Markdown-only test artifact for a Mermaid diagram renderer in a chat UI.

Hard constraints:
- Output ONLY Markdown.
- No prose outside headings and code fences.
- Every diagram must be in fenced code blocks using exactly:
  - ```mermaid
- Do not use placeholders like "..."
- Include at least 24 total Mermaid blocks.
- Prioritize diagrams that can be wide/tall to stress scrolling behavior.

Create sections in this exact order:

# Valid Examples
Include working examples that cover:
1. `flowchart` (LR and TD variants), including subgraphs and edge labels.
2. `sequenceDiagram` with many participants/messages, notes, loops, alt/opt/par blocks.
3. `classDiagram` with inheritance, composition, aggregation, interfaces, methods.
4. `stateDiagram-v2` with composite states and transitions.
5. `erDiagram` with entities, attributes, relationships, cardinalities.
6. `gantt` with multiple sections, dependencies, milestones, date formats.
7. `pie` with title and many slices.
8. `journey` diagram with multiple actors/sections.
9. `gitGraph` with branches, commits, merges, cherry-picks.
10. `mindmap` with at least 3 levels and many siblings.
11. `timeline` with multiple eras and events.
12. `quadrantChart` with axis labels and multiple points.
13. `sankey-beta` (if supported by Mermaid version).
14. `xychart-beta` (if supported), with labels and multiple series.
15. One very wide sequence diagram (20+ participants).
16. One very tall flowchart/state diagram (40+ nodes/transitions).
17. One diagram that includes unicode labels.
18. One diagram that includes long node text requiring wrapping.

# Scroll Stress Cases
Include 6 dedicated diagrams for layout/scroll stress:
1. very wide sequence diagram
2. very wide class diagram
3. very wide ER diagram
4. very tall flowchart
5. dense state diagram
6. dense mindmap

For each stress diagram, keep syntax valid and intentionally large.

# Theme/Style Cases
Include valid diagrams with Mermaid init blocks to exercise styling:
- `%%{init: {'theme':'default'}}%%`
- `%%{init: {'theme':'dark'}}%%`
- one with custom `themeVariables`

# Invalid Examples
Include exactly 10 intentionally broken Mermaid blocks to trigger parser/error UI paths:
1. unknown diagram type
2. malformed flowchart arrow syntax
3. unclosed subgraph
4. invalid sequence participant declaration
5. malformed class relationship
6. malformed state transition
7. invalid ER cardinality syntax
8. malformed gantt date/task line
9. malformed pie declaration
10. random text that is not Mermaid

Final check before output:
- Ensure valid blocks are truly parseable Mermaid.
- Ensure invalid blocks are clearly invalid.
- Ensure output is only Markdown with headings + mermaid fences.

---

# Mermaid Rendering Prompt (Short Mode)

You are generating a compact Markdown-only Mermaid rendering test sheet.

Hard constraints:
- Output ONLY Markdown.
- No explanations.
- Use only fenced code blocks with language `mermaid`.
- Produce exactly 10 blocks total:
  - 7 valid
  - 3 invalid

# Valid Examples
Create 7 valid blocks that collectively cover:
1. flowchart
2. sequenceDiagram (wide)
3. classDiagram
4. stateDiagram-v2
5. erDiagram
6. gantt
7. pie or mindmap

Also ensure across valid blocks:
- one intentionally wide diagram for horizontal scroll testing
- one intentionally tall diagram for vertical growth testing
- one with long labels/text wrapping
- one with unicode labels
- one with Mermaid init theme config

# Invalid Examples
Create exactly 3 invalid blocks:
1. malformed flowchart syntax
2. malformed sequence diagram syntax
3. unknown diagram type

Final check:
- exactly 10 blocks
- parser-realistic syntax
- no placeholder text
- output only Markdown
