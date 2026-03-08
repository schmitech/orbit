Generate a Markdown math rendering stress test for TOPIC.

  Requirements:
  1) Output only Markdown (no explanations).
  2) Include both inline math ($...$) and display math (\[...\]).
  3) Include at least 40 formulas total.
  4) Mix simple, intermediate, and advanced notation.
  5) Include:
  - fractions, roots, powers, subscripts/superscripts
  - sums/products, limits, derivatives, integrals
  - matrices, piecewise functions, cases
  - Greek letters and special symbols
  - at least 5 multiline aligned equations
  - at least 5 intentionally long expressions
  - at least 5 formulas with nested delimiters
  6) Include a section “Edge Cases” with tricky syntax that should still render:
  - escaped symbols, \text{...}, \left...\right, \boxed, \cancel (if supported)
  - improper integrals, double/triple integrals, contour integrals
  - mixed text+math sentences and line breaks
  7) Include one malformed section “Invalid Examples” with 8 broken formulas (missing delimiter, bad nesting, unmatched braces) for
  negative testing.
  8) Keep everything self-contained, no code fences.

  Topic: TOPIC

  Swap TOPIC with things like:

  1. Linear algebra
  2. Real analysis
  3. Complex analysis
  4. Probability/statistics
  5. Differential equations
  6. Abstract algebra
  7. Number theory
  8. Vector calculus