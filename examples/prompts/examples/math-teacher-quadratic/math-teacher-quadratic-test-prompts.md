# Quadratic Tutor Agent — Sample Test Prompts

Use these prompts to test the **Quadratic Functions Specialist** agent (see `math-teacher-quadratic-prompt.md`). Send each prompt to the LLM with that persona loaded; then render the model’s reply with the **Markdown renderer** (math + charts enabled) and check the items below.

---

## 1. Math rendering (inline & display)

**Prompt:**  
*"What's the quadratic formula? Write it in a way I can copy."*

**What to check:**
- Inline math in `$...$` (e.g. $x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}$ or equivalent).
- Display math in `$$...$$` for the full formula.
- Fractions, square root, and ± render correctly in the UI (no raw LaTeX).

---

## 2. Vertex by completing the square

**Prompt:**  
*"How do I find the vertex of y = x² - 4x + 1? Show steps."*

**What to check:**
- Step-by-step explanation with **completing the square**.
- All equations in LaTeX (e.g. $y = x^2 - 4x + 4 - 4 + 1$, $(x-2)^2 - 3$, vertex $(2, -3)$).
- Casual voice and light emojis.
- Optional: mention $x = -\frac{b}{2a}$ as an alternative.

---

## 3. Chart — basic parabola

**Prompt:**  
*"Can you graph f(x) = x² for me? I want to see the shape."*

**What to check:**
- Reply includes a **chart code block** with \`\`\`chart.
- Config: `type: line`, `title`, and optionally `xAxisLabel` / `yAxisLabel`.
- Data table: header row, separator row (e.g. `|----|------|`), then numeric rows (e.g. x from -2 to 2, f(x) = x²).
- Rendered chart shows a parabola (U-shape), not raw code.

---

## 4. Chart — shifted parabola with reference line

**Prompt:**  
*"Graph f(x) = (x - 1)² - 4 and show the axis of symmetry."*

**What to check:**
- \`\`\`chart block with `type: line` and a table for $(x-1)^2 - 4$.
- **referenceLines** with a vertical line at $x = 1$ (e.g. `{"x": 1, "label": "axis x=1", ...}`).
- Axis of symmetry appears as a dashed vertical line on the chart.
- Vertex $(1, -4)$ is clearly in the data range.

---

## 5. Table of values (no chart)

**Prompt:**  
*"Give me a table of coordinates for y = x² - 4 from x = -2 to 2."*

**What to check:**
- Response uses a **normal Markdown table** (not a chart block): `| x | y |`, header, then rows.
- Values are correct (e.g. $(-2, 0)$, $(-1, -3)$, $(0, -4)$, $(1, -3)$, $(2, 0)$).
- No \`\`\`chart block here (tables for “coordinates” / “points” stay as Markdown tables per the prompt).

---

## 6. Quadratic formula — solving an equation

**Prompt:**  
*"Solve x² - 5x + 6 = 0. Use the quadratic formula."*

**What to check:**
- Identifies $a = 1$, $b = -5$, $c = 6$.
- Substitutes into the formula with LaTeX.
- Simplifies to $x = 2$ and $x = 3$ (or equivalent).
- Encouraging tone; may mention factoring as another option.

---

## 7. Discriminant — number and type of roots

**Prompt:**  
*"How many solutions does x² - 4x + 5 = 0 have? How do you know without solving?"*

**What to check:**
- Defines or uses **discriminant** $b^2 - 4ac$ (or $D$) in LaTeX.
- Computes $(-4)^2 - 4(1)(5) = -4 < 0$.
- Correct conclusion: **no real solutions** (or two complex), explained clearly.
- Optional: brief link to the graph (parabola not crossing the x-axis).

---

## 8. Transformations (vertex form)

**Prompt:**  
*"What do a, h, and k do in f(x) = a(x - h)² + k? Give a quick example."*

**What to check:**
- Explains: $a$ (opens up/down, stretch/shrink), $h$ (horizontal shift), $k$ (vertical shift).
- Uses LaTeX for the vertex form and maybe one example (e.g. $f(x) = 2(x-3)^2 + 1$).
- Casual, clear language; may include a small sketch or suggest “want me to graph one?”.

---

## 9. Word problem — projectile or max

**Prompt:**  
*"A ball is thrown with h(t) = -16t² + 32t. When does it hit the ground? What’s the max height?"*

**What to check:**
- Interprets “hit the ground” as $h(t) = 0$ and “max height” as the vertex.
- Solves using factoring or the quadratic formula (roots $t = 0$, $t = 2$) and vertex at $t = 1$, $h = 16$.
- Uses LaTeX for equations and final answers.
- Brief real-world interpretation (e.g. vertex = max height, roots = when it hits the ground).

---

## 10. Request a graph after an explanation

**Prompt:**  
*"Find the vertex of y = -x² + 4x - 1. Then sketch the graph."*

**What to check:**
- Finds vertex $(2, 3)$ (or equivalent) with steps in LaTeX.
- **Then** includes a \`\`\`chart block: `type: line`, table for $-x^2 + 4x - 1$ around the vertex.
- Optional: reference line at $x = 2$ (axis of symmetry) or at $y = 3$.
- Rendered chart shows a downward-opening parabola with vertex visible.

---

## 11. Out-of-scope (honest redirect)

**Prompt:**  
*"How do I find the derivative of x²?"*  
or  
*"Solve this system: x² + y² = 25 and x + y = 7."*

**What to check:**
- Politely says this is **calculus** or **not purely quadratics** (or similar).
- Does **not** give a full calculus or systems solution.
- Suggests what the agent *can* help with (e.g. graphing $y = x^2$, vertex, roots of quadratics).

---

## 12. Voice and tone

**Prompt:**  
*"I keep confusing the vertex and the roots. Help?"*

**What to check:**
- Explains **vertex** (max/min point) vs **roots** (x-intercepts / zeros) clearly.
- Uses **bold** for key terms, LaTeX for formulas (e.g. vertex $(h,k)$, roots where $f(x)=0$).
- Casual, friendly tone (“here’s the thing,” “you got this,” etc.).
- Light, natural emoji use (e.g. ✅ 🎯 💡).
- Offers a next step (e.g. “want to try one and find both?”).

---

## 13. Comparing two parabolas (multiple series)

**Prompt:**
*"Graph f(x) = x² and g(x) = (x - 2)² on the same chart so I can see the shift."*

**What to check:**
- Chart uses **multiple y-columns**: `| x | f(x) | g(x) |` (not two separate charts).
- Legend appears showing both function names with different colors.
- `xAxisType: number` used for proper numeric scaling.
- Visually shows the horizontal shift (g is f shifted right by 2).

---

## 14. Chart with horizontal reference line

**Prompt:**
*"Graph y = x² - 4 and mark where it crosses the x-axis."*

**What to check:**
- Chart includes a **horizontal reference line** at `y: 0` (e.g. `{"y": 0, "label": "y = 0", ...}`).
- Roots at $x = -2$ and $x = 2$ are visible where the parabola crosses the reference line.
- Optional: vertical reference line at axis of symmetry ($x = 0$).
- `xAxisType: number` for proper scaling.

---

## 15. Domain/range discussion (KaTeX macros)

**Prompt:**
*"What's the domain and range of f(x) = x² - 3? Use proper math notation."*

**What to check:**
- Uses **set notation** with KaTeX macros: `\RR` for real numbers (renders as $\mathbb{R}$).
- Domain: all real numbers, e.g. $x \in \RR$ or $(-\infty, \infty)$.
- Range: $y \geq -3$ or $[-3, \infty)$, explained via vertex.
- LaTeX renders correctly (no raw `\RR` or `\mathbb{R}` visible).

---

## 16. Chart with description subtitle

**Prompt:**
*"Graph f(x) = -2(x + 1)² + 3. Label it clearly with the vertex info."*

**What to check:**
- Chart has a `title:` (e.g. the function equation).
- Chart has a `description:` line (e.g. "Vertex at (-1, 3), opens downward").
- Reference lines for axis of symmetry ($x = -1$) and/or vertex level ($y = 3$).
- Parabola opens **downward** (due to $a = -2$).
- `xAxisType: number` used.

---

## Quick reference: what the renderer supports

| Feature | In the reply | Renders as |
|---------|--------------|------------|
| Inline math | `$x = -\frac{b}{2a}$` | KaTeX inline |
| Display math | `$$f(x) = ax^2 + bx + c$$` | KaTeX block |
| KaTeX macros | `$x \in \RR$` | $x \in \mathbb{R}$ |
| Chart | ` ```chart ` with type + table | Interactive line/bar/etc. |
| Chart description | `description: Vertex at (2, 3)` | Subtitle under title |
| xAxisType | `xAxisType: number` | Proper numeric axis scaling |
| Vertical ref line | `{"x": 2, "label": "...", ...}` | Dashed vertical line |
| Horizontal ref line | `{"y": 0, "label": "...", ...}` | Dashed horizontal line |
| Multiple series | `\| x \| f(x) \| g(x) \|` | Multiple curves + legend |
| Table | Markdown `\| x \| y \|` | GFM table |

Use these prompts to verify math rendering, chart generation (including reference lines, multiple series, axis types), table usage, and persona. If any response doesn't format correctly, check that the app is passing the reply through the same Markdown renderer used by the demo (with math and charts enabled).
