// Test case for tables that start on their own line but without a blank line before them
// This is common in LLM responses where text is followed immediately by a table
export const llmTableWithoutBlankLine = `Here's a comparison of popular programming languages:
| Language      | Primary Use Case                     | Popularity (2025) | Learning Curve | Key Features                          |
|---------------|--------------------------------------|-------------------|----------------|---------------------------------------|
| **Python**    | Web dev, AI/ML, scripting, data analysis | ★★★★★ (Top 1)     | Easy           | Simple syntax, huge libraries (NumPy, Pandas) |
| **JavaScript**| Web development (frontend/backend)    | ★★★★★ (Top 2)     | Medium         | Runs in browsers, versatile frameworks (React, Node.js) |
| **Java**      | Enterprise apps, Android dev          | ★★★★☆             | Hard           | Strong typing, object-oriented, scalable |
| **C++**       | Game engines, high-performance apps   | ★★★☆☆             | Hard           | Low-level control, speed, memory management |
| **R**         | Statistics, data visualization        | ★★★☆☆             | Medium         | Specialized for analytics, ggplot2 library |
| **Go**        | Cloud services, microservices         | ★★★★☆             | Easy           | Fast compilation, concurrency support |
| **Swift**     | iOS/macOS app development             | ★★★☆☆             | Medium         | Modern syntax, Apple ecosystem focus |

The table above shows the key differences between these languages.`;

export const llmInlineTableContent = `## Inline Table Response

These emojis came from an LLM answer that kept the table header on the same line as the prose, which previously failed to render:
| Object   | Description                                                                 | Colors                                                                 | Notable Features                                                                 |
|----------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| **Apple** | Whole red apple with a green leaf attached to the stem                     | Red (apple), green (leaf)                                               | Fresh appearance, leaf attached to stem                                             |
| **Book**  | Closed book with a dark blue cover and a lighter beige spine              | Dark blue (cover), beige (spine)                                         | Rectangular shape, typical book design                                            |
| **Bicycle** | Red bicycle with black tires and a black seat                             | Red (frame), black (tires, seat)                                         | Classic design, upright seating position                                          |
| **Cat**   | Tabby cat sitting upright with striped coat                                | Brown/black stripes, greenish-yellow eyes                              | Feline fur pattern, upright posture                                                |
| **Pizza** | Pepperoni pizza with a golden crust and red pepperoni slices              | Golden brown (crust), red (pepperoni)                                    | Classic pizza toppings, melted cheese (inferred)                                   |
| **Shoe**  | Gray sneaker with white soles and black laces                             | Gray (upper), white (sole), black (laces)                               | Casual design, athletic styling                                                    |

The renderer should normalize the table onto its own line so ReactMarkdown can render it even when used inside another application.`;

export const ellipsoidFlatteningContent = `## Ellipsoid Flattening Example

In navigation we often approximate the Earth as an oblate spheroid where it’s treated like a circle of radius $b$. (More accurate ellipsoid formulas exist if you want them.)

Using flattening $f$:

$f = \\frac{a-b}{a} \\qquad\\Longrightarrow\\qquad b = a(1-f)$

So the circumferences in terms of $a$ and $f$ are:

$$
\\begin{aligned}
C_{\\text{equatorial}} &= 2\\pi a \\\\
C_{\\text{polar}} &\\approx 2\\pi b = 2\\pi a(1-f)
\\end{aligned}
$$

This snippet covers several inline variables like $a$, $b$, and $f$ that must remain math to avoid regressions.`;

export const sphereSurfaceContent = `## Surface Equation (3D)

A sphere centered at the origin:

$x^2 + y^2 + z^2 = R^2$

### Parameterization (latitude/longitude)
Using latitude $\\phi$ and longitude $\\lambda$:

\\begin{aligned}
x &= R\\cos\\phi \\cos\\lambda \\\\
y &= R\\cos\\phi \\sin\\lambda \\\\
z &= R\\sin\\phi
\\end{aligned}

### Curvature (how "bent" it is)
For a sphere, the (principal) curvatures are constant:

$k_1 = k_2 = \\frac{1}{R}$

### Surface drop approximation
If you travel a distance $s$ along Earth's surface (an arc), the central angle is:

$\\theta = \\frac{s}{R}$

If you stand on a tangent line and look at how much the surface falls away over ground distance $s$, a common approximation is:

$\\text{drop} \\approx \\frac{s^2}{2R}$`;

export const languageShowcaseContent = `# Programming Language Showcase

Quick references for a variety of syntaxes so syntax highlighting and code block rendering can be validated across ecosystems.

### Rust
\`\`\`rust
fn fibonacci(n: u32) -> u32 {
    match n {
        0 | 1 => n,
        _ => fibonacci(n - 1) + fibonacci(n - 2),
    }
}

fn main() {
    println!("fib(10) = {}", fibonacci(10));
}
\`\`\`

### Go
\`\`\`go
package main

import "fmt"

func worker(id int, jobs <-chan int) {
    for job := range jobs {
        fmt.Printf("worker %d handling job %d\\n", id, job)
    }
}

func main() {
    jobs := make(chan int, 2)
    go worker(1, jobs)
    jobs <- 1
    jobs <- 2
    close(jobs)
}
\`\`\`

### Java
\`\`\`java
public record User(String id, String email) {}

public class UserService {
    public Optional<User> find(String id) {
        return Optional.of(new User(id, id + "@example.com"));
    }
}
\`\`\`

### Kotlin
\`\`\`kotlin
data class Session(val id: String, val isActive: Boolean)

fun List<Session>.activeCount() = count { it.isActive }
\`\`\`

### Swift
\`\`\`swift
struct Person: Identifiable {
    let id = UUID()
    let name: String
}

let team = [Person(name: "Ada"), Person(name: "Grace")]
print(team.map(\\.name).joined(separator: ", "))
\`\`\`

### C#
\`\`\`csharp
public static async Task<IEnumerable<string>> LoadAsync(HttpClient client, IEnumerable<string> urls)
{
    var tasks = urls.Select(url => client.GetStringAsync(url));
    return await Task.WhenAll(tasks);
}
\`\`\`

### C++
\`\`\`cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{1, 2, 3};
    for (auto value : values) {
        std::cout << value << std::endl;
    }
    return 0;
}
\`\`\`

### PHP
\`\`\`php
<?php

function greet(string $name = "world"): string {
    return sprintf("Hello, %s!", ucfirst($name));
}

echo greet("markdown");
\`\`\`

### Ruby
\`\`\`ruby
class Queue
  def initialize
    @items = []
  end

  def push(item)
    @items << item
  end
end
\`\`\`

### Bash
\`\`\`bash
#!/usr/bin/env bash

set -euo pipefail

for file in *.md; do
  echo "Linting $file"
done
\`\`\`

### PowerShell
\`\`\`powershell
$Path = "C:\\\\logs"
Get-ChildItem -Path $Path -Filter "*.log" | ForEach-Object {
  Write-Host "Found $($_.Name)"
}
\`\`\`

### SQL
\`\`\`sql
WITH recent_orders AS (
  SELECT id, total, status, created_at
  FROM orders
  WHERE created_at >= NOW() - INTERVAL '30 days'
)
SELECT status, COUNT(*)
FROM recent_orders
GROUP BY status;
\`\`\`

### GraphQL
\`\`\`graphql
query UserDetail($id: ID!) {
  user(id: $id) {
    id
    name
    teams {
      id
      name
    }
  }
}
\`\`\`

### JSON
\`\`\`json
{
  "service": "inventory",
  "version": 3,
  "features": ["restock", "reservations", "alerts"]
}
\`\`\`

### YAML
\`\`\`yaml
environments:
  production:
    region: us-east-1
    replicas: 6
  staging:
    region: us-west-2
    replicas: 2
\`\`\`

### MATLAB
\`\`\`matlab
function y = damped_sine(x, damping)
    y = exp(-damping * x) .* sin(x);
end
\`\`\`

### R
\`\`\`r
library(dplyr)

summary <- iris %>%
  group_by(Species) %>%
  summarise(across(everything(), mean))
\`\`\`
`;

export type CodeSample = {
  language: string;
  description: string;
  markdown: string;
  preview: string;
};

export const codeSampleLibrary: CodeSample[] = [
  {
    language: 'Rust',
    description: 'Ownership, borrowing, and iterator pipelines.',
    markdown: `### Rust Iterator Sample

\`\`\`rust
fn total_length(values: &[String]) -> usize {
    values.iter().map(|value| value.len()).sum()
}

fn main() {
    let values = vec![String::from("foo"), String::from("bar")];
    println!("{}", total_length(&values));
}
\`\`\`
`,
    preview: `fn total_length(values: &[String]) -> usize {\n    values.iter().map(|value| value.len()).sum()\n}`,
  },
  {
    language: 'Go',
    description: 'Goroutines communicating over buffered channels.',
    markdown: `### Go Routine Sample

\`\`\`go
package main

import "fmt"

func main() {
    jobs := make(chan int, 3)
    go func() {
        for job := range jobs {
            fmt.Println("job", job)
        }
    }()
    jobs <- 1
    jobs <- 2
    close(jobs)
}
\`\`\`
`,
    preview: `jobs := make(chan int, 3)\ngo func() {\n    for job := range jobs {\n        fmt.Println("job", job)\n    }\n}()`,
  },
  {
    language: 'Kotlin',
    description: 'Extension function using data classes and null safety.',
    markdown: `### Kotlin DSL Sample

\`\`\`kotlin
data class Feature(val name: String, val enabled: Boolean = true)

fun Collection<Feature>.enabledNames() =
    filter { it.enabled }.joinToString { it.name }
\`\`\`
`,
    preview: `fun Collection<Feature>.enabledNames() =\n    filter { it.enabled }.joinToString { it.name }`,
  },
  {
    language: 'Swift',
    description: 'SwiftUI inspired struct with computed property.',
    markdown: `### Swift Struct Sample

\`\`\`swift
struct Report {
    let name: String
    var pages: Int

    var summary: String {
        "\\\\(name) contains \\\\(pages) pages"
    }
}
\`\`\`
`,
    preview: `struct Report {\n    let name: String\n    var pages: Int\n\n    var summary: String {\n        "\\(name) contains \\(pages) pages"\n    }\n}`,
  },
  {
    language: 'C#',
    description: 'Async LINQ query with record types.',
    markdown: `### C# Async Enumerable

\`\`\`csharp
public record Invoice(int Id, decimal Amount);

public async IAsyncEnumerable<Invoice> LoadInvoicesAsync(HttpClient client) {
    var ids = Enumerable.Range(1, 3);
    foreach (var id in ids) {
        var amount = decimal.Parse(await client.GetStringAsync($"/invoices/{id}"));
        yield return new Invoice(id, amount);
    }
}
\`\`\`
`,
    preview: `public record Invoice(int Id, decimal Amount);\n\npublic async IAsyncEnumerable<Invoice> LoadInvoicesAsync(HttpClient client) {`,
  },
  {
    language: 'PHP',
    description: 'Named arguments and concise arrow functions.',
    markdown: `### PHP Collection Helpers

\`\`\`php
$totals = array_map(
    fn (int $value) => $value * 2,
    range(1, 5)
);

print_r($totals);
\`\`\`
`,
    preview: `$totals = array_map(\n    fn (int $value) => $value * 2,\n    range(1, 5)\n);`,
  },
  {
    language: 'SQL',
    description: 'Window functions measuring revenue momentum.',
    markdown: `### SQL Window Functions

\`\`\`sql
SELECT
  region,
  month,
  revenue,
  SUM(revenue) OVER (PARTITION BY region ORDER BY month) AS running_total
FROM sales;
\`\`\`
`,
    preview: `SUM(revenue) OVER (PARTITION BY region ORDER BY month) AS running_total`,
  },
  {
    language: 'Bash',
    description: 'Strict shell script iterating with guards.',
    markdown: `### Bash Strict Mode

\`\`\`bash
#!/usr/bin/env bash
set -euo pipefail

while read -r line; do
  [[ -z "$line" ]] && continue
  echo "-> $line"
done < input.txt
\`\`\`
`,
    preview: `set -euo pipefail\n\nwhile read -r line; do\n  [[ -z "$line" ]] && continue`,
  },
  {
    language: 'JSON',
    description: 'Sample configuration for feature flags.',
    markdown: `### JSON Feature Flags

\`\`\`json
{
  "featureFlags": {
    "betaDashboard": true,
    "reranking": {
      "enabled": true,
      "weight": 0.42
    }
  }
}
\`\`\`
`,
    preview: `"reranking": {\n  "enabled": true,\n  "weight": 0.42\n}`,
  },
  {
    language: 'YAML',
    description: 'Deployment manifest with anchors.',
    markdown: `### YAML Template

\`\`\`yaml
defaults: &defaults
  retries: 3
  timeout: 30s

jobs:
  deploy:
    <<: *defaults
    region: eu-central-1
\`\`\`
`,
    preview: `defaults: &defaults\n  retries: 3\n  timeout: 30s`,
  },
];

export const testCases = [
  {
    title: 'Basic Markdown',
    content: `# Heading 1
## Heading 2
### Heading 3

This is a paragraph with **bold text** and *italic text* and ***bold italic text***.

Here's a [link to Google](https://google.com) and some \`inline code\`.

- Unordered list item 1
- Unordered list item 2
  - Nested item
  - Another nested item
- Unordered list item 3

1. Ordered list item 1
2. Ordered list item 2
   1. Nested ordered item
   2. Another nested ordered item
3. Ordered list item 3

> This is a blockquote.
> It can span multiple lines.

---

Horizontal rule above.`
  },
  {
    title: 'HTML Line Breaks',
    content: `## Testing HTML Break Tags

Standard joke with inline HTML:
Why don't skeletons fight each other?<br>They don't have the guts.

Multiple sequential breaks in a paragraph:
First line<br/>Second line<br />Third line

Numbered instructions using breaks instead of markdown:
1)<br>Gather supplies
2)<br>Build the prototype
3)<br>Celebrate the win

Mixed content with bold text and breaks:
**Reminder:** Ship the feature by EOD.<br><br>Escalate if blocked.`
  },
  {
    title: 'Code Blocks',
    content: `## Code Examples

Here's some inline code: \`const x = 42;\`

\`\`\`javascript
// JavaScript code block
function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

console.log(fibonacci(10));
\`\`\`

\`\`\`python
# Python code block
def hello_world():
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello_world()
\`\`\`

\`\`\`typescript
// TypeScript with type annotations
interface User {
  id: number;
  name: string;
  email?: string;
}

const getUser = async (id: number): Promise<User> => {
  const response = await fetch(\`/api/users/\${id}\`);
  return response.json();
};
\`\`\``
  },
  {
    title: 'Programming Language Showcase',
    content: languageShowcaseContent,
  },
  {
    title: 'Inline Code (Single Backticks)',
    content: `## Inline Code Test

This test case verifies that text surrounded by single backticks (\`word\`) renders as inline code and NOT as full code blocks.

### Basic Inline Code

Here's a simple example: \`const x = 42;\` should appear inline.

### Multiple Inline Code Snippets

You can have multiple inline code snippets like \`variable\`, \`function()\`, and \`class\` in the same paragraph.

### Inline Code in Lists

- Item with \`code\` in it
- Another item with \`inline\` code
- List item containing \`multiple\` \`code\` \`snippets\`

### Inline Code in Different Contexts

**Bold text with \`code\` inside** and *italic text with \`code\` too*.

### Edge Cases

- Single character: \`x\`
- Multiple words: \`this is code\`
- With punctuation: \`code!\`, \`code?\`, \`code.\`
- Empty backticks should not break: \`\` (empty)
- Code at start: \`start\` of sentence
- Code at end: end of sentence \`end\`

### Mixed with Block Code

Here's inline code: \`inline\` and here's a block:

\`\`\`javascript
// This should be a block
const block = true;
\`\`\`

And more inline: \`more inline\` code.

### Real-world Example

When using \`OP_HUSKY\`, \`PROJECT_X\`, \`CYBER_OPS\`, \`COUNTER_FRAUD\`, and \`INTEL_ANALYSIS\` compartments, ensure proper access controls.

Compartment Access Failures: 53 denials involved users lacking proper need-to-know for compartments including \`OP_HUSKY\`, \`PROJECT_X\`, \`CYBER_OPS\`, \`COUNTER_FRAUD\`, and \`INTEL_ANALYSIS\`.

Classification Escalation Attempts: 42 denials where users attempted to access documents classified \`SECRET\` or \`TOP_SECRET\`.`
  },
  {
    title: 'Tables (GFM)',
    content: `## Tables

| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1-1 | Cell 1-2 | Cell 1-3 |
| Cell 2-1 | Cell 2-2 | Cell 2-3 |
| Cell 3-1 | Cell 3-2 | Cell 3-3 |

### Aligned Table

| Left Aligned | Center Aligned | Right Aligned |
|:------------|:--------------:|--------------:|
| Left        | Center         | Right         |
| Lorem       | Ipsum          | Dolor         |
| Sit         | Amet           | Consectetur   |`
  },
  {
    title: 'LLM Inline Table Response',
    content: llmInlineTableContent,
  },
  {
    title: 'LLM Table Without Blank Line',
    content: llmTableWithoutBlankLine,
  },
  {
    title: 'Wide Tables (Horizontal Scrolling)',
    content: `## Wide Tables for Horizontal Scrolling Test

This test case demonstrates horizontal scrolling with tables that have many columns.

### Wide Data Table (10 Columns)
| ID | Name | Email | Phone | Address | City | State | ZIP | Country | Status |
|----|------|-------|-------|---------|------|-------|-----|---------|--------|
| 1 | John Doe | john.doe@example.com | (555) 123-4567 | 123 Main St | New York | NY | 10001 | USA | Active |
| 2 | Jane Smith | jane.smith@example.com | (555) 234-5678 | 456 Oak Ave | Los Angeles | CA | 90001 | USA | Active |
| 3 | Bob Johnson | bob.johnson@example.com | (555) 345-6789 | 789 Pine Rd | Chicago | IL | 60601 | USA | Inactive |
| 4 | Alice Williams | alice.williams@example.com | (555) 456-7890 | 321 Elm St | Houston | TX | 77001 | USA | Active |
| 5 | Charlie Brown | charlie.brown@example.com | (555) 567-8901 | 654 Maple Dr | Phoenix | AZ | 85001 | USA | Pending |

### Very Wide Financial Table (15 Columns)
| Date | Transaction ID | Description | Category | Amount | Currency | Payment Method | Merchant | Account | Balance | Tax | Fee | Net Amount | Status | Notes | Reference |
|------|----------------|-------------|----------|--------|----------|----------------|----------|---------|---------|-----|-----|------------|--------|-------|-----------|
| 2024-01-15 | TXN-001 | Grocery Store Purchase | Food | $125.50 | USD | Credit Card | Whole Foods | Checking | $2,450.00 | $10.04 | $0.00 | $135.54 | Completed | Weekly groceries | REF-001 |
| 2024-01-16 | TXN-002 | Gas Station | Transportation | $45.00 | USD | Debit Card | Shell | Checking | $2,405.00 | $3.60 | $0.00 | $48.60 | Completed | Fuel | REF-002 |
| 2024-01-17 | TXN-003 | Restaurant | Food | $78.90 | USD | Credit Card | Olive Garden | Checking | $2,326.10 | $6.31 | $0.00 | $85.21 | Completed | Dinner | REF-003 |
| 2024-01-18 | TXN-004 | Online Subscription | Entertainment | $14.99 | USD | Credit Card | Netflix | Checking | $2,311.11 | $1.20 | $0.00 | $16.19 | Completed | Monthly subscription | REF-004 |
| 2024-01-19 | TXN-005 | Utility Bill | Utilities | $156.78 | USD | Bank Transfer | Electric Company | Checking | $2,154.33 | $0.00 | $2.50 | $159.28 | Completed | January bill | REF-005 |

### Ultra-Wide Analytics Table (20 Columns)
| Timestamp | User ID | Session ID | Page | Action | Device | Browser | OS | Country | City | Referrer | Campaign | Source | Medium | Duration | Bounce | Conversion | Revenue | Product | Category |
|-----------|---------|------------|------|--------|--------|---------|----|---------|------|----------|----------|--------|--------|----------|--------|------------|---------|---------|----------|
| 2024-01-15 10:30:22 | U-12345 | SESS-001 | /home | pageview | Desktop | Chrome | Windows | USA | New York | google.com | spring-sale | google | cpc | 245 | No | Yes | $99.99 | Widget A | Electronics |
| 2024-01-15 10:35:18 | U-12346 | SESS-002 | /products | click | Mobile | Safari | iOS | USA | Los Angeles | facebook.com | summer-promo | facebook | social | 180 | No | No | $0.00 | - | - |
| 2024-01-15 10:42:55 | U-12347 | SESS-003 | /checkout | purchase | Desktop | Firefox | Windows | Canada | Toronto | direct | - | direct | none | 320 | No | Yes | $149.99 | Widget B | Electronics |
| 2024-01-15 10:51:12 | U-12348 | SESS-004 | /about | pageview | Tablet | Safari | iPadOS | UK | London | bing.com | brand-campaign | bing | cpc | 95 | Yes | No | $0.00 | - | - |
| 2024-01-15 11:05:33 | U-12349 | SESS-005 | /cart | add_to_cart | Desktop | Edge | Windows | Germany | Berlin | twitter.com | influencer | twitter | social | 210 | No | No | $0.00 | Widget C | Accessories |

### Comparison Table with Many Metrics (12 Columns)
| Product | Price | Rating | Reviews | Sales (Q1) | Sales (Q2) | Sales (Q3) | Sales (Q4) | Total Revenue | Profit Margin | Market Share | Growth % |
|---------|-------|--------|---------|------------|------------|------------|------------|---------------|---------------|--------------|----------|
| Product A | $99.99 | 4.5 | 1,234 | $125,000 | $145,000 | $165,000 | $180,000 | $615,000 | 35% | 12.5% | +15% |
| Product B | $149.99 | 4.7 | 2,456 | $180,000 | $210,000 | $240,000 | $270,000 | $900,000 | 42% | 18.3% | +22% |
| Product C | $79.99 | 4.2 | 856 | $95,000 | $110,000 | $125,000 | $140,000 | $470,000 | 28% | 9.6% | +12% |
| Product D | $199.99 | 4.9 | 3,789 | $250,000 | $290,000 | $330,000 | $380,000 | $1,250,000 | 48% | 25.4% | +28% |
| Product E | $59.99 | 4.0 | 567 | $75,000 | $85,000 | $95,000 | $105,000 | $360,000 | 25% | 7.3% | +8% |

### Project Management Table (14 Columns)
| Task ID | Task Name | Assignee | Priority | Status | Start Date | Due Date | Estimated Hours | Actual Hours | Progress | Dependencies | Tags | Notes | Project | Milestone |
|---------|-----------|----------|---------|--------|------------|----------|-----------------|--------------|----------|--------------|------|-------|---------|-----------|
| TASK-001 | Design Homepage | Alice | High | In Progress | 2024-01-01 | 2024-01-15 | 40 | 32 | 80% | - | design, frontend | Initial mockups complete | Website Redesign | M1 |
| TASK-002 | Implement API | Bob | High | Completed | 2024-01-05 | 2024-01-20 | 60 | 58 | 100% | TASK-001 | backend, api | All endpoints tested | Website Redesign | M1 |
| TASK-003 | Write Tests | Charlie | Medium | In Progress | 2024-01-10 | 2024-01-25 | 30 | 18 | 60% | TASK-002 | testing, qa | Unit tests done | Website Redesign | M2 |
| TASK-004 | Deploy to Staging | David | Medium | Pending | 2024-01-20 | 2024-01-30 | 8 | 0 | 0% | TASK-003 | devops, deployment | Waiting for approval | Website Redesign | M2 |
| TASK-005 | User Documentation | Eve | Low | Not Started | 2024-01-25 | 2024-02-05 | 20 | 0 | 0% | TASK-004 | documentation | - | Website Redesign | M3 |

### Summary
These wide tables should demonstrate:
- ✅ Horizontal scrolling when tables exceed container width
- ✅ Proper column alignment and spacing
- ✅ Readable content even with many columns
- ✅ Responsive behavior on different screen sizes`
  },
  {
    title: 'Math Notation',
    content: `## Mathematical Expressions

### Inline Math
The quadratic formula is $x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$ which solves $ax^2 + bx + c = 0$.

Einstein's famous equation: $E = mc^2$

### Display Math
$$
\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}
$$

### Complex Equations
$$
\\begin{aligned}
\\nabla \\times \\vec{\\mathbf{B}} -\\, \\frac1c\\, \\frac{\\partial\\vec{\\mathbf{E}}}{\\partial t} &= \\frac{4\\pi}{c}\\vec{\\mathbf{j}} \\\\
\\nabla \\cdot \\vec{\\mathbf{E}} &= 4 \\pi \\rho \\\\
\\nabla \\times \\vec{\\mathbf{E}}\\, +\\, \\frac1c\\, \\frac{\\partial\\vec{\\mathbf{B}}}{\\partial t} &= \\vec{\\mathbf{0}} \\\\
\\nabla \\cdot \\vec{\\mathbf{B}} &= 0
\\end{aligned}
$$

### Greek Letters and Symbols
$\\alpha, \\beta, \\gamma, \\delta, \\epsilon, \\theta, \\lambda, \\mu, \\pi, \\sigma, \\omega$

$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$

$\\lim_{x \\to \\infty} \\frac{1}{x} = 0$`
  },
  {
    title: 'Ellipsoid Flattening Math',
    content: ellipsoidFlatteningContent,
  },
  {
    title: 'Sphere Surface Math',
    content: sphereSurfaceContent,
  },
  {
    title: 'Matrix & Vector Math',
    content: `## Matrix and Vector Notation

### Position Vector with Matrix

Let the Galactic Center be the origin, and assume the Sun moves in a circle of radius $R_0$ with constant angular speed $\\Omega$.

$$
\\vec{r}_{\\odot}(t) = \\begin{pmatrix} R_0\\cos(\\Omega t+\\phi_0)\\\\ R_0\\sin(\\Omega t+\\phi_0)\\\\ 0 \\end{pmatrix}
$$

### Inline Matrix Expression

The position vector $\\vec{r}_{\\odot}(t) = \\begin{pmatrix} x \\\\ y \\\\ z \\end{pmatrix}$ describes a circular orbit.

### Rotation Matrix

A 2D rotation by angle $\\theta$:

$$
R(\\theta) = \\begin{pmatrix} \\cos\\theta & -\\sin\\theta \\\\ \\sin\\theta & \\cos\\theta \\end{pmatrix}
$$

### Transformation with Brackets

Using bracket matrix notation:

$$
\\begin{bmatrix} x' \\\\ y' \\end{bmatrix} = \\begin{bmatrix} a & b \\\\ c & d \\end{bmatrix} \\begin{bmatrix} x \\\\ y \\end{bmatrix}
$$

### System of Equations (Cases)

The piecewise function:

$$
f(x) = \\begin{cases} x^2 & \\text{if } x \\geq 0 \\\\ -x^2 & \\text{if } x < 0 \\end{cases}
$$

### Determinant

The determinant of a 3×3 matrix:

$$
\\det(A) = \\begin{vmatrix} a_{11} & a_{12} & a_{13} \\\\ a_{21} & a_{22} & a_{23} \\\\ a_{31} & a_{32} & a_{33} \\end{vmatrix}
$$

### Standalone Environment (No Delimiters)

This should auto-wrap in display math:

\\begin{aligned}
\\vec{F} &= m\\vec{a} \\\\
\\vec{p} &= m\\vec{v} \\\\
E &= \\frac{1}{2}mv^2
\\end{aligned}

### Edge Case: Bracket Delimiters with Content

Using backslash-bracket notation with expressions before the matrix:

\\[
\\vec{v} = \\begin{pmatrix} v_x \\\\ v_y \\\\ v_z \\end{pmatrix}
\\]

### Edge Case: Matrix in Display Math with Prefix

$$
A^{-1} = \\frac{1}{\\det(A)} \\begin{bmatrix} d & -b \\\\ -c & a \\end{bmatrix}
$$

### Edge Case: Multiple Matrices in One Expression

$$
\\begin{pmatrix} x' \\\\ y' \\end{pmatrix} = \\begin{pmatrix} \\cos\\theta & -\\sin\\theta \\\\ \\sin\\theta & \\cos\\theta \\end{pmatrix} \\begin{pmatrix} x \\\\ y \\end{pmatrix} + \\begin{pmatrix} t_x \\\\ t_y \\end{pmatrix}
$$

### Edge Case: Nested Environments

$$
\\begin{cases}
\\vec{F} = m\\vec{a} & \\text{Newton's 2nd Law} \\\\
\\begin{aligned}
F_x &= ma_x \\\\
F_y &= ma_y
\\end{aligned} & \\text{Component form}
\\end{cases}
$$

### Edge Case: Small Inline Matrix

The identity matrix $I = \\begin{pmatrix} 1 & 0 \\\\ 0 & 1 \\end{pmatrix}$ is fundamental.

### Edge Case: Currency Near Math

The matrix operation costs \\$500 to compute: $\\begin{pmatrix} a & b \\end{pmatrix}$.
`
  },
  {
    title: 'Undo Button Antiderivatives',
    content: `## Antiderivative Walkthrough

4) The "undo button" idea: antiderivatives

An indefinite integral

$\\int f(x)\\,dx$
means: "Find a function whose derivative is $f(x)$."

If $F'(x) = f(x)$, then

$\\int f(x)\\,dx = F(x) + C$

Compute:

$\\int 2x\\,dx$

Step 1: Find the antiderivative

$\\int 2x\\,dx = x^2 + C$`
  },
  {
    title: 'Chemistry Notation',
    content: `## Chemistry Examples

### Chemical Formulas
Water molecule: $\\ce{H2O}$

Sulfuric acid: $\\ce{H2SO4}$

Complex ion: $\\ce{[Cu(NH3)4]^{2+}}$

### Chemical Equations
Combustion of methane:
$$\\ce{CH4 + 2O2 -> CO2 + 2H2O}$$

Equilibrium reaction:
$$\\ce{N2 + 3H2 <=> 2NH3}$$

Redox reaction:
$$\\ce{Zn + Cu^{2+} -> Zn^{2+} + Cu}$$

### Organic Chemistry
Benzene ring: $\\ce{C6H6}$

Ethanol: $\\ce{CH3CH2OH}$

Glucose: $\\ce{C6H12O6}$`
  },
  {
    title: 'Currency Handling',
    content: `## Currency vs Math

### Currency Examples
The price is $5.99 for a single item.

Budget range: $1,000 - $5,000

Total cost: $12,345.67

Negative balance: -$500.00

In parentheses: ($1,234.56)

With suffixes: $1.2k, $3.5M, $2.8B

### Math with Dollar Signs
The variable $x$ represents the unknown value.

Given $f(x) = x^2 + 3x - 4$, find $f(2)$.

The set $S = \\{1, 2, 3, 4, 5\\}$ contains five elements.

### Mixed Content
If an item costs $10 and you buy $n$ items, the total cost is $10n$ dollars.

The formula $P = 2\\pi r$ gives the perimeter, which costs $5 per meter to fence.`
  },
  {
    title: 'Edge Cases',
    content: `## Edge Cases and Special Characters

### Escaping
This is a literal asterisk: \\*

This is a literal dollar sign: \\$

Escaped backticks: \\\`code\\\`

### Special Characters
Arrows: → ← ↑ ↓ ⇒ ⇐ ⇔

Math symbols: ≤ ≥ ≠ ≈ ∞ ∈ ∉ ⊂ ⊃ ∪ ∩

Other: © ® ™ € £ ¥ ° ± × ÷

### Empty Math Blocks

Inline empty: $$

Display empty:

$$
$$

### Nested Formatting

**Bold with *italic* inside**

*Italic with **bold** inside*

> Blockquote with **bold** and *italic* and \`code\`

### Long URLs

Check out this really long URL: https://www.example.com/very/long/path/that/goes/on/and/on/and/on/with/many/parameters?param1=value1&param2=value2&param3=value3&param4=value4`
  },
  {
    title: 'Graphs and Diagrams',
    content: `## Graph Rendering

### Mermaid Flowchart
\`\`\`mermaid
graph TD
    A[Start] --> B{Is it working?}
    B -->|Yes| C[Great!]
    B -->|No| D[Debug]
    D --> B
    C --> E[End]
\`\`\`

### Mermaid Sequence Diagram
\`\`\`mermaid
sequenceDiagram
    participant User
    participant App
    participant API
    User->>App: Request data
    App->>API: Fetch data
    API-->>App: Return data
    App-->>User: Display results
\`\`\`

### Mixed Content: Graphs with Math and Currency
The algorithm costs $500 to run and has complexity $O(n \\log n)$:

\`\`\`mermaid
graph LR
    A[Input: x] --> B[Process: f of x]
    B --> C{Cost check}
    C -->|Yes| D[Output]
    C -->|No| E[Optimize]
    E --> B
\`\`\`

The diagram above shows the processing flow where input $x$ goes through function $f(x) = x^2$.

The chemical reaction rate constant $k$ follows:
$$k = A \\cdot e^{-E_a/RT}$$

Budget breakdown with pricing in markdown:
- Development: $22,500 (45%)
- Testing: $12,500 (25%)
- Documentation: $7,500 (15%)
- Deployment: $7,500 (15%)

\`\`\`mermaid
pie title Project Budget Distribution
    "Development" : 45
    "Testing" : 25
    "Documentation" : 15
    "Deployment" : 15
\`\`\``
  },
  {
    title: 'Music Notation (ABC)',
    content: `## ABC Music Notation Examples

### ABC Notation - Simple Example
\`\`\`abc
X:1
T:Little Study in C
M:4/4
L:1/4
K:C
C D E F | G G E E | D C D E | C2 C2 |
\`\`\`

### ABC Notation - More Complex Example
\`\`\`abc
X:2
T:Amazing Grace
M:3/4
L:1/8
K:G
G2 GA B2 | c2 B2 A2 | G2 GA B2 | A4 G2 |
G2 GA B2 | c2 B2 A2 | G4 z2 |]
\`\`\`

### Using the 'music' Language Identifier
You can also use \`music\` as the language identifier for ABC notation:

\`\`\`music
X:3
T:Test Tune
M:4/4
K:C
C D E F G A B c |
\`\`\`
`,
  },
  {
    title: 'SVG Graphics',
    content: `## SVG Graphics Examples

SVG (Scalable Vector Graphics) allows for crisp, resolution-independent graphics. These examples demonstrate various SVG features including gradients, filters, patterns, clipping, animations, and more.

### Analytics Dashboard Icon
\`\`\`svg
<svg width="240" height="180" xmlns="http://www.w3.org/2000/svg">
  <!-- Background -->
  <rect width="240" height="180" fill="#f8fafc" rx="8"/>
  <!-- Bar Chart -->
  <rect x="30" y="120" width="30" height="40" fill="#3b82f6" rx="4"/>
  <rect x="70" y="90" width="30" height="70" fill="#8b5cf6" rx="4"/>
  <rect x="110" y="70" width="30" height="90" fill="#ec4899" rx="4"/>
  <rect x="150" y="100" width="30" height="60" fill="#f59e0b" rx="4"/>
  <rect x="190" y="110" width="30" height="50" fill="#10b981" rx="4"/>
  <!-- Trend Line -->
  <polyline points="45,130 85,105 125,85 165,115 205,120"
            fill="none" stroke="#ef4444" stroke-width="3"
            stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Data Points -->
  <circle cx="45" cy="130" r="5" fill="#ef4444" stroke="#fff" stroke-width="2"/>
  <circle cx="85" cy="105" r="5" fill="#ef4444" stroke="#fff" stroke-width="2"/>
  <circle cx="125" cy="85" r="5" fill="#ef4444" stroke="#fff" stroke-width="2"/>
  <circle cx="165" cy="115" r="5" fill="#ef4444" stroke="#fff" stroke-width="2"/>
  <circle cx="205" cy="120" r="5" fill="#ef4444" stroke="#fff" stroke-width="2"/>
  <!-- Title -->
  <text x="120" y="25" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="16" font-weight="bold" fill="#1e293b">Revenue Growth</text>
  <!-- Legend -->
  <circle cx="30" cy="45" r="4" fill="#ef4444"/>
  <text x="40" y="49" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Trend</text>
</svg>
\`\`\`

### Progress Ring with Gradient
\`\`\`svg
<svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="50%" stop-color="#8b5cf6"/>
      <stop offset="100%" stop-color="#ec4899"/>
    </linearGradient>
  </defs>
  <circle cx="100" cy="100" r="80" fill="none" stroke="#e5e7eb" stroke-width="12"/>
  <circle cx="100" cy="100" r="80" fill="none" stroke="url(#progressGradient)"
          stroke-width="12" stroke-linecap="round"
          stroke-dasharray="377" stroke-dashoffset="94"
          transform="rotate(-90 100 100)"/>
  <text x="100" y="95" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="32" font-weight="bold" fill="#1f2937">75%</text>
  <text x="100" y="120" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="14" fill="#6b7280">Complete</text>
</svg>
\`\`\`

### Glowing Button with Filter
\`\`\`svg
<svg width="200" height="80" viewBox="0 0 200 80" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <linearGradient id="buttonGradient" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#60a5fa"/>
      <stop offset="100%" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <rect x="20" y="15" width="160" height="50" rx="25"
        fill="url(#buttonGradient)" filter="url(#glow)"/>
  <text x="100" y="47" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="16" font-weight="bold" fill="white">Get Started</text>
</svg>
\`\`\`

### Decorative Pattern Background
\`\`\`svg
<svg width="240" height="120" viewBox="0 0 240 120" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
      <circle cx="10" cy="10" r="2" fill="#cbd5e1"/>
    </pattern>
    <pattern id="grid" x="0" y="0" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e2e8f0" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="240" height="120" fill="url(#grid)"/>
  <rect width="240" height="120" fill="url(#dots)" opacity="0.5"/>
  <rect x="40" y="30" width="160" height="60" rx="8" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>
  <text x="120" y="68" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="18" font-weight="600" fill="#1e293b">Pattern Demo</text>
</svg>
\`\`\`

### Profile Avatar with Clip Path
\`\`\`svg
<svg width="150" height="150" viewBox="0 0 150 150" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="avatarClip">
      <circle cx="75" cy="75" r="65"/>
    </clipPath>
    <linearGradient id="avatarBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ddd6fe"/>
      <stop offset="100%" stop-color="#c4b5fd"/>
    </linearGradient>
  </defs>
  <circle cx="75" cy="75" r="72" fill="none" stroke="#8b5cf6" stroke-width="4"/>
  <circle cx="75" cy="75" r="65" fill="url(#avatarBg)"/>
  <g clip-path="url(#avatarClip)">
    <circle cx="75" cy="55" r="25" fill="#7c3aed"/>
    <ellipse cx="75" cy="130" rx="45" ry="40" fill="#7c3aed"/>
  </g>
  <circle cx="115" cy="115" r="15" fill="#fff"/>
  <circle cx="115" cy="115" r="12" fill="#22c55e"/>
</svg>
\`\`\`

### Animated Spinner
\`\`\`svg
<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="spinnerGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#3b82f6" stop-opacity="0"/>
      <stop offset="100%" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" stroke-width="8"/>
  <circle cx="50" cy="50" r="40" fill="none" stroke="url(#spinnerGradient)"
          stroke-width="8" stroke-linecap="round"
          stroke-dasharray="200" stroke-dashoffset="150"
          transform="rotate(0 50 50)">
    <animateTransform attributeName="transform" type="rotate"
                      from="0 50 50" to="360 50 50" dur="1s" repeatCount="indefinite"/>
  </circle>
</svg>
\`\`\`

### Arrow Diagram with Markers
\`\`\`svg
<svg width="300" height="150" viewBox="0 0 300 150" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#6366f1"/>
    </marker>
  </defs>
  <rect x="20" y="50" width="70" height="40" rx="6" fill="#eef2ff" stroke="#6366f1" stroke-width="2"/>
  <text x="55" y="75" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#4338ca">Input</text>
  <rect x="120" y="50" width="70" height="40" rx="6" fill="#eef2ff" stroke="#6366f1" stroke-width="2"/>
  <text x="155" y="75" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#4338ca">Process</text>
  <rect x="220" y="50" width="70" height="40" rx="6" fill="#eef2ff" stroke="#6366f1" stroke-width="2"/>
  <text x="255" y="75" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#4338ca">Output</text>
  <line x1="90" y1="70" x2="118" y2="70" stroke="#6366f1" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="190" y1="70" x2="218" y2="70" stroke="#6366f1" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="150" y="25" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="14" font-weight="bold" fill="#1e293b">Data Flow</text>
</svg>
\`\`\`

### Network Topology with Shadows
\`\`\`svg
<svg width="320" height="240" viewBox="0 0 320 240" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="serverGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#60a5fa"/>
      <stop offset="100%" stop-color="#3b82f6"/>
    </linearGradient>
    <linearGradient id="clientGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#a78bfa"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="2" dy="2" stdDeviation="3" flood-opacity="0.2"/>
    </filter>
  </defs>
  <text x="160" y="25" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="16" font-weight="bold" fill="#1e293b">Network Architecture</text>
  <line x1="160" y1="75" x2="70" y2="150" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>
  <line x1="160" y1="75" x2="160" y2="150" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>
  <line x1="160" y1="75" x2="250" y2="150" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>
  <g filter="url(#shadow)">
    <rect x="130" y="45" width="60" height="45" rx="6" fill="url(#serverGrad)"/>
    <rect x="140" y="55" width="40" height="4" rx="2" fill="#fff" opacity="0.6"/>
    <rect x="140" y="63" width="40" height="4" rx="2" fill="#fff" opacity="0.6"/>
    <rect x="140" y="71" width="40" height="4" rx="2" fill="#fff" opacity="0.6"/>
    <circle cx="175" cy="80" r="3" fill="#22c55e"/>
  </g>
  <text x="160" y="105" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#475569">Server</text>
  <g filter="url(#shadow)">
    <rect x="40" y="140" width="60" height="45" rx="6" fill="url(#clientGrad)"/>
    <rect x="50" y="148" width="40" height="25" rx="2" fill="#fff" opacity="0.3"/>
    <rect x="60" y="178" width="20" height="3" rx="1" fill="#fff" opacity="0.5"/>
  </g>
  <text x="70" y="200" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#475569">Client A</text>
  <g filter="url(#shadow)">
    <rect x="130" y="140" width="60" height="45" rx="6" fill="url(#clientGrad)"/>
    <rect x="140" y="148" width="40" height="25" rx="2" fill="#fff" opacity="0.3"/>
    <rect x="150" y="178" width="20" height="3" rx="1" fill="#fff" opacity="0.5"/>
  </g>
  <text x="160" y="200" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#475569">Client B</text>
  <g filter="url(#shadow)">
    <rect x="220" y="140" width="60" height="45" rx="6" fill="url(#clientGrad)"/>
    <rect x="230" y="148" width="40" height="25" rx="2" fill="#fff" opacity="0.3"/>
    <rect x="240" y="178" width="20" height="3" rx="1" fill="#fff" opacity="0.5"/>
  </g>
  <text x="250" y="200" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#475569">Client C</text>
  <rect x="20" y="215" width="12" height="12" rx="2" fill="url(#serverGrad)"/>
  <text x="37" y="225" font-family="Arial, sans-serif" font-size="10" fill="#64748b">Server</text>
  <rect x="90" y="215" width="12" height="12" rx="2" fill="url(#clientGrad)"/>
  <text x="107" y="225" font-family="Arial, sans-serif" font-size="10" fill="#64748b">Client</text>
</svg>
\`\`\`

### Curved Text Path
\`\`\`svg
<svg width="280" height="140" viewBox="0 0 280 140" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <path id="textCurve" d="M 20 100 Q 140 20 260 100" fill="none"/>
    <linearGradient id="textGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f472b6"/>
      <stop offset="50%" stop-color="#a78bfa"/>
      <stop offset="100%" stop-color="#60a5fa"/>
    </linearGradient>
  </defs>
  <path d="M 20 100 Q 140 20 260 100" fill="none" stroke="#e2e8f0" stroke-width="2" stroke-dasharray="4,4"/>
  <text font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="url(#textGrad)">
    <textPath href="#textCurve" startOffset="50%" text-anchor="middle">
      Follow the Curve
    </textPath>
  </text>
  <circle cx="20" cy="100" r="6" fill="#f472b6"/>
  <circle cx="260" cy="100" r="6" fill="#60a5fa"/>
</svg>
\`\`\`
`,
  },
  {
    title: 'Charts and Data Visualization',
    content: `## Interactive Charts

### Simple Bar Chart
\`\`\`chart
type: bar
title: Q1 Sales Performance
data: [45000, 52000, 48000]
labels: [January, February, March]
colors: [#3b82f6, #8b5cf6, #ec4899]
\`\`\`

### Table-based Line Chart
\`\`\`chart
type: line
title: Revenue Growth Over Time
| Month | Revenue | Expenses |
|-------|---------|----------|
| Jan   | 100000  | 80000    |
| Feb   | 150000  | 90000    |
| Mar   | 200000  | 110000   |
| Apr   | 180000  | 105000   |
| May   | 220000  | 115000   |
| Jun   | 250000  | 120000   |
\`\`\`

### Pie Chart - Market Share
\`\`\`chart
type: pie
title: Market Share by Product
data: [35, 25, 20, 15, 5]
labels: [Product A, Product B, Product C, Product D, Others]
\`\`\`

### Area Chart - User Growth
\`\`\`chart
type: area
title: Monthly Active Users
| Month | Users  | Premium |
|-------|--------|---------|
| Jan   | 10000  | 1000    |
| Feb   | 15000  | 1500    |
| Mar   | 22000  | 2200    |
| Apr   | 28000  | 3000    |
| May   | 35000  | 4000    |
| Jun   | 42000  | 5200    |
\`\`\`

### Multi-Series Bar Chart
\`\`\`chart
type: bar
title: Department Performance Comparison
| Department | Q1    | Q2    | Q3    | Q4    |
|------------|-------|-------|-------|-------|
| Sales      | 45000 | 52000 | 48000 | 60000 |
| Marketing  | 35000 | 38000 | 42000 | 45000 |
| Support    | 25000 | 28000 | 30000 | 32000 |
\`\`\`

### Stacked Bar with Targets
\`\`\`chart
type: bar
title: Quarterly Subscription Revenue
description: Comparing new business vs expansion ARR with a quarterly goal.
stacked: true
showLegend: true
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
referenceLines: [{"y":80000,"label":"Quarterly Goal","color":"#d946ef","strokeDasharray":"6 3"}]
| Quarter | New ARR | Expansion ARR |
|---------|---------|----------------|
| Q1      | 32000   | 18000          |
| Q2      | 36000   | 21000          |
| Q3      | 38000   | 22000          |
| Q4      | 42000   | 26000          |
\`\`\`

### Dual Axis Line Chart
\`\`\`chart
type: line
title: Office Climate & Humidity
showLegend: true
xAxisLabel: Month
yAxisLabel: Temperature (°F)
yAxisRightLabel: Humidity (%)
series: [
  {"key":"Temperature","name":"Temperature","color":"#f97316","yAxisId":"left","strokeWidth":3},
  {"key":"Humidity","name":"Humidity","color":"#0ea5e9","yAxisId":"right","strokeWidth":2}
]
| Month | Temperature | Humidity |
|-------|-------------|----------|
| Jan   | 68          | 40       |
| Feb   | 70          | 38       |
| Mar   | 72          | 42       |
| Apr   | 74          | 48       |
| May   | 76          | 50       |
| Jun   | 78          | 55       |
\`\`\`

### Composed Pipeline Chart
\`\`\`chart
type: composed
title: Quarterly Pipeline Health
description: Combining bars, lines, and scatter to show pipeline progression.
showLegend: true
xAxisLabel: Stage
series: [
  {"key":"Leads","type":"bar","name":"Leads","color":"#3b82f6"},
  {"key":"Opportunities","type":"bar","name":"Opportunities","color":"#10b981"},
  {"key":"Conversion","type":"line","name":"Conversion %","color":"#f59e0b","yAxisId":"right","strokeWidth":3},
  {"key":"Avg Deal","type":"scatter","name":"Avg Deal","color":"#a855f7","yAxisId":"right"}
]
yAxisLabel: Volume
yAxisRightLabel: %
| Stage        | Leads | Opportunities | Conversion | Avg Deal |
|--------------|-------|---------------|------------|----------|
| Awareness    | 1200  | 300           | 0.25       | 15000    |
| Consideration| 800   | 240           | 0.30       | 21000    |
| Proposal     | 400   | 140           | 0.35       | 26000    |
| Negotiation  | 220   | 90            | 0.41       | 31000    |
| Closed Won   | 120   | 70            | 0.58       | 38000    |
\`\`\`

### Scatter Plot with Trend Line
\`\`\`chart
type: scatter
title: NPS vs Expansion Spend
description: Customer loyalty plotted against new upsell dollars.
showGrid: true
xKey: NPS
xAxisLabel: Net Promoter Score
yAxisLabel: Expansion Revenue ($)
referenceLines: [{"x":50,"label":"Neutral NPS","color":"#9ca3af"}]
| NPS | Expansion |
|-----|-----------|
| 20  | 12000     |
| 35  | 18000     |
| 45  | 26000     |
| 55  | 34000     |
| 60  | 42000     |
| 75  | 52000     |
| 80  | 61000     |
\`\`\`

### Compact KPI Sparkline
\`\`\`chart
type: area
title: Daily Active Devices
description: Compact formatting keeps the axis readable even with large counts.
formatter: {"format":"compact","minimumFractionDigits":1,"maximumFractionDigits":1}
| Day | Active Devices |
|-----|----------------|
| Mon | 154000         |
| Tue | 162000         |
| Wed | 158000         |
| Thu | 171000         |
| Fri | 185000         |
| Sat | 192000         |
| Sun | 178000         |
\`\`\`

### Real-world Example with Context
Our Q2 revenue reached $250,000, representing a 14% increase from Q1. Here's the breakdown:

\`\`\`chart
type: bar
title: Q2 Revenue by Channel
data: [85000, 95000, 70000]
labels: [Direct Sales, Online, Partners]
colors: [#10b981, #3b82f6, #f59e0b]
\`\`\`

The online channel showed the strongest growth at $95,000, driven by our new e-commerce platform launch in Q1.`
  },
  {
    title: 'Real-world Example',
    content: `# Project Documentation

## Overview
This project implements a **machine learning model** for predicting housing prices using the formula:

$$\\text{Price} = \\beta_0 + \\beta_1 \\cdot \\text{Area} + \\beta_2 \\cdot \\text{Bedrooms} + \\epsilon$$

## Installation

\`\`\`bash
npm install @schmitech/markdown-renderer
# or
yarn add @schmitech/markdown-renderer
\`\`\`

## API Reference

### \`preprocessMarkdown(content: string): string\`

Preprocesses markdown content to handle currency and math notation correctly.

**Parameters:**
- \`content\` - The raw markdown string

**Returns:** Processed markdown string

### Example Usage

\`\`\`typescript
import { MarkdownRenderer } from '@schmitech/markdown-renderer';

function App() {
  const content = "The cost is $100 and the formula is $x^2$";
  return <MarkdownRenderer content={content} />;
}
\`\`\`

## Performance Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Render Time | 15ms | < 20ms |
| Bundle Size | 45KB | < 50KB |
| Memory Usage | 2.3MB | < 5MB |

## Chemical Reactions in the Process

The oxidation process follows: $\\ce{2H2O2 -> 2H2O + O2}$

## Pricing

- Basic Plan: $9.99/month
- Pro Plan: $29.99/month
- Enterprise: $99.99/month

> **Note:** All prices are in USD. Mathematical models show ROI of $r = 1.5x$ where $x$ is your investment.`
  },
  {
    title: 'Vertical Scrolling Test',
    content: `# Vertical Scrolling Test

This test case demonstrates **vertical scrolling** with very long content. All content should scroll vertically instead of being truncated.

---

## Very Long Paragraph

${'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. '.repeat(30)}

---

## Long Code Block

\`\`\`javascript
// This is a very long code block to test vertical scrolling
${Array(80).fill(null).map((_, i) => `function exampleFunction${i}() {
  const variable${i} = "This is line ${i} of a very long code block";
  console.log("Processing item ${i}");
  const data${i} = {
    id: ${i},
    name: "Item ${i}",
    description: "This is a detailed description for item ${i} that contains a lot of text to make the code block longer",
    metadata: {
      created: new Date(),
      updated: new Date(),
      tags: ["tag1", "tag2", "tag3", "tag4", "tag5"],
      properties: {
        color: "blue",
        size: "large",
        weight: ${i * 10},
        category: "test"
      }
    },
    process: function() {
      return this.id * 2;
    }
  };
  return data${i};
}`).join('\n\n')}
\`\`\`

---

## Long Table (Many Rows)

| ID | Name | Description | Status | Created | Updated | Version | Tags | Notes |
|----|------|-------------|--------|---------|---------|---------|------|-------|
${Array(100).fill(null).map((_, i) => `| ${i + 1} | Item ${i + 1} | This is a detailed description for item ${i + 1} that contains multiple sentences and lots of information about its properties and characteristics. | ${i % 3 === 0 ? 'Active' : i % 3 === 1 ? 'Pending' : 'Inactive'} | 2024-01-${String((i % 28) + 1).padStart(2, '0')} | 2024-01-${String((i % 28) + 1).padStart(2, '0')} | 1.${i} | tag1, tag2, tag3 | This item has additional notes that provide more context and information. |`).join('\n')}

---

## Long Math Content

${Array(25).fill(null).map((_, i) => `### Equation ${i + 1}

The formula for calculation ${i + 1} is:

$$x_${i} = \\sum_{j=0}^{${i}} \\frac{${i} \\cdot j}{j+1} + \\int_0^{${i}} e^{-t^2} dt$$

This can be simplified to:

$$x_${i} = \\frac{${i}(${i}+1)}{2} \\cdot \\frac{\\sqrt{\\pi}}{2} \\text{erf}(${i})$$

Where $\\text{erf}(x)$ is the error function defined as:

$$\\text{erf}(x) = \\frac{2}{\\sqrt{\\pi}} \\int_0^x e^{-t^2} dt$$

The relationship between these functions can be expressed as:

$$\\lim_{n \\to \\infty} \\sum_{i=0}^{n} x_i = \\frac{\\pi}{2}$$

`).join('\n')}

---

## Long List Content

${Array(150).fill(null).map((_, i) => `- Item ${i + 1}: This is a detailed list item that contains a lot of information. It describes various aspects of the item including its properties, characteristics, and relationships to other items in the system. The content is intentionally long to test vertical scrolling capabilities. Each item should be fully visible and the list should scroll smoothly.`).join('\n')}

---

## Mixed Long Content

### Section 1: Narrative Text

${'Once upon a time, in a land far, far away, there lived a developer who was building a markdown renderer. This developer wanted to ensure that long content would scroll properly instead of being truncated. They tested various scenarios including long paragraphs, code blocks, tables, and mathematical expressions. The goal was to create a seamless user experience where content of any length could be viewed comfortably. '.repeat(40)}

### Section 2: TypeScript Code Examples

\`\`\`typescript
${Array(60).fill(null).map((_, i) => `// Example ${i + 1}
interface Example${i} {
  id: number;
  name: string;
  description: string;
  metadata: {
    created: Date;
    updated: Date;
    version: string;
    tags: string[];
    properties: {
      color: string;
      size: string;
      weight: number;
      category: string;
    };
  };
}

const example${i}: Example${i} = {
  id: ${i},
  name: "Example ${i}",
  description: "This is example ${i} with detailed description that explains its purpose and usage",
  metadata: {
    created: new Date(),
    updated: new Date(),
    version: "1.0.${i}",
    tags: ["tag1", "tag2", "tag3"],
    properties: {
      color: "blue",
      size: "large",
      weight: ${i * 10},
      category: "test"
    }
  }
};

function processExample${i}(example: Example${i}): string {
  return \`Processing \${example.name} with ID \${example.id}\`;
}`).join('\n\n')}
\`\`\`

### Section 3: Data Table

| ID | Name | Description | Status | Created | Updated | Version | Tags |
|----|------|-------------|--------|---------|---------|---------|------|
${Array(75).fill(null).map((_, i) => `| ${i} | Item ${i} | This is a detailed description for item ${i} that contains multiple sentences and lots of information about its properties and characteristics. The description is intentionally long to test how tables handle vertical scrolling. | ${i % 3 === 0 ? 'Active' : i % 3 === 1 ? 'Pending' : 'Inactive'} | 2024-01-${String((i % 28) + 1).padStart(2, '0')} | 2024-01-${String((i % 28) + 1).padStart(2, '0')} | 1.${i} | tag1, tag2, tag3 |`).join('\n')}

---

## Summary

This test case should demonstrate:
- ✅ Long paragraphs scroll vertically
- ✅ Long code blocks scroll vertically
- ✅ Long tables scroll vertically
- ✅ Long lists scroll vertically
- ✅ Long math content scrolls vertically
- ✅ Mixed long content scrolls properly
- ✅ The page remains usable even with very long content
- ✅ No content is truncated or cut off`
  },
  {
    title: 'Robust Charts Test',
    content: `## Robust Chart Rendering Test

This test case validates that charts render correctly with complete data sets. It tests various chart types and configurations that should always render fully.

### Line Chart - Revenue Trend

\`\`\`chart
type: line
title: Monthly Revenue Trend
description: Single metric line chart showing revenue over 12 months
showLegend: false
xAxisLabel: Month
yAxisLabel: Revenue ($)
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
| Month | Revenue |
|-------|---------|
| January | 15234 |
| February | 14567 |
| March | 16789 |
| April | 14052 |
| May | 18234 |
| June | 19567 |
| July | 17234 |
| August | 14789 |
| September | 16123 |
| October | 19012 |
| November | 22345 |
| December | 25678 |
\`\`\`

### Multi-Metric Chart with Dual Axes

When you have metrics with different scales (e.g., revenue in thousands vs order count in hundreds), use a composed chart with dual Y-axes:

\`\`\`chart
type: composed
title: E-commerce Performance Overview
description: Revenue on left axis, order metrics on right axis
showLegend: true
xAxisLabel: Month
yAxisLabel: Revenue ($)
yAxisRightLabel: Count
series: [
  {"key":"Revenue","type":"area","name":"Revenue ($)","color":"#3b82f6","opacity":0.3},
  {"key":"Orders","type":"line","name":"Total Orders","color":"#10b981","yAxisId":"right","strokeWidth":2},
  {"key":"Customers","type":"line","name":"Unique Customers","color":"#f59e0b","yAxisId":"right","strokeWidth":2}
]
| Month | Revenue | Orders | Customers |
|-------|---------|--------|-----------|
| January | 15234 | 156 | 142 |
| February | 14567 | 143 | 128 |
| March | 16789 | 168 | 155 |
| April | 14052 | 125 | 118 |
| May | 18234 | 189 | 172 |
| June | 19567 | 201 | 185 |
| July | 17234 | 178 | 163 |
| August | 14789 | 145 | 132 |
| September | 16123 | 167 | 154 |
| October | 19012 | 198 | 181 |
| November | 22345 | 223 | 205 |
| December | 25678 | 256 | 234 |
\`\`\`

### Multi-Line Chart (Similar Scales)

For metrics with similar scales, a regular line chart works well:

\`\`\`chart
type: line
title: Order Metrics Comparison
description: Comparing orders vs unique customers (similar scale)
showLegend: true
xAxisLabel: Month
yAxisLabel: Count
| Month | Total Orders | Unique Customers |
|-------|--------------|------------------|
| January | 156 | 142 |
| February | 143 | 128 |
| March | 168 | 155 |
| April | 125 | 118 |
| May | 189 | 172 |
| June | 201 | 185 |
| July | 178 | 163 |
| August | 145 | 132 |
| September | 167 | 154 |
| October | 198 | 181 |
| November | 223 | 205 |
| December | 256 | 234 |
\`\`\`

### Bar Chart with Multiple Series

\`\`\`chart
type: bar
title: Quarterly Revenue by Region
description: Regional performance comparison across all quarters
showLegend: true
stacked: false
| Quarter | North America | Europe | Asia Pacific | Latin America |
|---------|---------------|--------|--------------|---------------|
| Q1 2024 | 125000 | 95000 | 78000 | 45000 |
| Q2 2024 | 145000 | 110000 | 92000 | 52000 |
| Q3 2024 | 132000 | 102000 | 85000 | 48000 |
| Q4 2024 | 168000 | 125000 | 105000 | 62000 |
\`\`\`

### Stacked Area Chart

\`\`\`chart
type: area
title: Traffic Sources Over Time
description: Breakdown of website traffic by source
showLegend: true
stacked: true
| Week | Organic | Paid | Social | Direct | Referral |
|------|---------|------|--------|--------|----------|
| W1 | 12000 | 8000 | 5000 | 4000 | 2000 |
| W2 | 14000 | 9500 | 6200 | 4200 | 2300 |
| W3 | 13500 | 8800 | 5800 | 4500 | 2100 |
| W4 | 15000 | 10000 | 6500 | 4800 | 2500 |
| W5 | 16500 | 11000 | 7000 | 5000 | 2800 |
| W6 | 18000 | 12000 | 7500 | 5200 | 3000 |
\`\`\`

### Pie Chart

\`\`\`chart
type: pie
title: Market Share by Product Category
data: [35, 28, 22, 10, 5]
labels: [Electronics, Clothing, Home & Garden, Sports, Other]
colors: [#3b82f6, #8b5cf6, #ec4899, #10b981, #f59e0b]
\`\`\`

### Composed Chart with Dual Axis

\`\`\`chart
type: composed
title: Revenue vs Profit Margin Analysis
description: Comparing absolute revenue with percentage margins
showLegend: true
series: [
  {"key":"Revenue","type":"bar","name":"Revenue ($K)","color":"#3b82f6"},
  {"key":"Cost","type":"bar","name":"Cost ($K)","color":"#ef4444"},
  {"key":"Margin","type":"line","name":"Profit Margin (%)","color":"#10b981","yAxisId":"right","strokeWidth":3}
]
yAxisLabel: Amount ($K)
yAxisRightLabel: Margin (%)
| Product | Revenue | Cost | Margin |
|---------|---------|------|--------|
| Product A | 150 | 95 | 36.7 |
| Product B | 220 | 130 | 40.9 |
| Product C | 180 | 120 | 33.3 |
| Product D | 280 | 155 | 44.6 |
| Product E | 120 | 85 | 29.2 |
\`\`\`

### Scatter Plot

\`\`\`chart
type: scatter
title: Customer Satisfaction vs Retention Rate
description: Each point represents a customer segment
showGrid: true
xKey: Satisfaction
xAxisLabel: Satisfaction Score (1-10)
yAxisLabel: Retention Rate (%)
| Satisfaction | Retention |
|--------------|-----------|
| 3.2 | 45 |
| 4.5 | 52 |
| 5.8 | 61 |
| 6.2 | 68 |
| 7.1 | 75 |
| 7.8 | 82 |
| 8.5 | 88 |
| 9.0 | 92 |
| 9.4 | 95 |
\`\`\`

### Chart with Reference Lines

\`\`\`chart
type: bar
title: Monthly Sales vs Target
description: Showing actual sales against quarterly targets
showLegend: true
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
referenceLines: [{"y":75000,"label":"Q1 Target","color":"#ef4444","strokeDasharray":"6 3"},{"y":85000,"label":"Q2 Target","color":"#f59e0b","strokeDasharray":"6 3"}]
| Month | Sales |
|-------|-------|
| Jan | 65000 |
| Feb | 72000 |
| Mar | 81000 |
| Apr | 78000 |
| May | 88000 |
| Jun | 92000 |
\`\`\`

### Expected Behavior

All charts above should:
- ✅ Display complete X-axis labels (no missing months/quarters)
- ✅ Show all data points connected properly
- ✅ Display legends when enabled
- ✅ Show tooltips on hover
- ✅ Render smoothly without flickering
- ✅ Handle window resize gracefully`
  },
  {
    title: 'X-Axis Label Handling (Many Data Points)',
    content: `## X-Axis Label Improvements Test

This test case validates the automatic handling of x-axis labels when there are many data points. The chart renderer should automatically:
- Rotate labels when there are more than 6 data points
- Truncate long labels when there are more than 4 data points AND average label length > 15 characters
- Show fewer labels (interval) when there are many data points
- Adjust bottom margin to accommodate rotated labels
- Show full original labels in tooltips even when axis labels are truncated
- Truncate at word boundaries when possible for better readability

### Bar Chart with Many Job Roles (15+ data points)

This chart tests label rotation, truncation, and interval display with many long category names. **Hover over the bars to see full job role names in tooltips** even when axis labels are truncated:

\`\`\`chart
type: bar
title: Average Salary by Job Role
description: Testing x-axis label handling with many data points and long labels
showLegend: true
xAxisLabel: Job Role
yAxisLabel: Avg Salary / Min Salary / Max Salary
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
| Job Role | Avg Salary | Min Salary | Max Salary |
|----------|------------|------------|------------|
| Sales Representative | 65000 | 45000 | 85000 |
| Engineering Sales Manager | 125000 | 95000 | 155000 |
| Operations Specialist | 72000 | 55000 | 90000 |
| Financial Analyst | 68000 | 50000 | 86000 |
| Marketing Manager | 95000 | 75000 | 115000 |
| Software Engineer | 110000 | 85000 | 135000 |
| Product Manager | 105000 | 80000 | 130000 |
| Data Scientist | 115000 | 90000 | 140000 |
| Business Development Representative | 58000 | 42000 | 74000 |
| Customer Success Manager | 78000 | 60000 | 96000 |
| Human Resources Coordinator | 55000 | 40000 | 70000 |
| Operations Manager | 88000 | 68000 | 108000 |
| Senior Software Engineer | 135000 | 110000 | 160000 |
| Technical Program Manager | 120000 | 95000 | 145000 |
| Director of Engineering | 165000 | 140000 | 190000 |
| Senior Product Manager | 140000 | 115000 | 165000 |
| Principal Software Engineer | 155000 | 130000 | 180000 |
| VP of Sales | 180000 | 150000 | 210000 |
\`\`\`

### Line Chart with Many Months (12+ data points)

This chart demonstrates label rotation and interval display:

\`\`\`chart
type: line
title: Monthly Revenue by Department
description: Testing x-axis labels with 12 months
showLegend: true
xAxisLabel: Month
yAxisLabel: Revenue ($)
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
| Month | Sales Department | Marketing Department | Support Department |
|-------|------------------|----------------------|---------------------|
| January | 125000 | 95000 | 75000 |
| February | 135000 | 102000 | 78000 |
| March | 128000 | 98000 | 72000 |
| April | 142000 | 110000 | 82000 |
| May | 150000 | 118000 | 88000 |
| June | 145000 | 112000 | 85000 |
| July | 138000 | 105000 | 80000 |
| August | 152000 | 120000 | 90000 |
| September | 148000 | 115000 | 87000 |
| October | 160000 | 125000 | 95000 |
| November | 155000 | 122000 | 92000 |
| December | 168000 | 132000 | 100000 |
\`\`\`

### Area Chart with Many Categories (20+ data points)

This chart tests the maximum label handling with many data points:

\`\`\`chart
type: area
title: Product Category Performance
description: Testing with 20+ categories to test label interval and rotation
showLegend: true
stacked: true
xAxisLabel: Product Category
yAxisLabel: Sales Volume
| Product Category | Online Sales | Retail Sales |
|------------------|-------------|--------------|
| Electronics and Computers | 125000 | 95000 |
| Clothing and Apparel | 98000 | 120000 |
| Home and Garden Supplies | 75000 | 85000 |
| Sports and Outdoor Equipment | 65000 | 72000 |
| Books and Media | 45000 | 55000 |
| Health and Beauty Products | 82000 | 78000 |
| Automotive Parts and Accessories | 68000 | 92000 |
| Toys and Games | 55000 | 68000 |
| Food and Beverages | 110000 | 135000 |
| Pet Supplies and Accessories | 42000 | 48000 |
| Office Supplies and Equipment | 58000 | 65000 |
| Furniture and Home Decor | 72000 | 88000 |
| Jewelry and Watches | 48000 | 62000 |
| Musical Instruments | 35000 | 42000 |
| Art and Craft Supplies | 28000 | 35000 |
| Baby Products and Gear | 52000 | 68000 |
| Tools and Hardware | 65000 | 78000 |
| Travel and Luggage | 38000 | 45000 |
| Fitness and Exercise Equipment | 72000 | 85000 |
| Kitchen and Dining Products | 68000 | 82000 |
| Outdoor and Camping Gear | 55000 | 65000 |
| Industrial and Scientific Supplies | 42000 | 52000 |
\`\`\`

### Bar Chart with Few Data Points (No Rotation)

This chart has fewer than 6 data points, so labels should remain horizontal:

\`\`\`chart
type: bar
title: Q1-Q4 Revenue Comparison
description: Few data points - labels should remain horizontal
showLegend: false
xAxisLabel: Quarter
yAxisLabel: Revenue ($)
formatter: {"format":"currency","currency":"USD","minimumFractionDigits":0}
| Quarter | Revenue |
|---------|---------|
| Q1 2024 | 450000 |
| Q2 2024 | 520000 |
| Q3 2024 | 480000 |
| Q4 2024 | 610000 |
\`\`\`

### Chart Testing Smart Truncation (Many Short Labels)

This chart has many data points but short labels - should NOT truncate unnecessarily:

\`\`\`chart
type: bar
title: Performance by Region Code
description: Testing smart truncation - many points but short labels shouldn't truncate
showLegend: false
xAxisLabel: Region
yAxisLabel: Score
| Region | Score |
|--------|-------|
| US | 95 |
| UK | 88 |
| CA | 92 |
| DE | 85 |
| FR | 87 |
| IT | 83 |
| ES | 81 |
| NL | 89 |
| SE | 91 |
| NO | 90 |
| DK | 88 |
| FI | 86 |
| AU | 93 |
| JP | 84 |
| KR | 82 |
\`\`\`

### Chart Testing Word-Boundary Truncation

This chart tests truncation at word boundaries for better readability. Notice that truncated labels break at word boundaries (e.g., "Human Resources..." instead of "Human Resourc..."). **Hover to see full department names in tooltips:**

\`\`\`chart
type: line
title: Department Performance Metrics
description: Testing word-boundary truncation with long multi-word labels
showLegend: true
height: 400
xAxisLabel: Department
yAxisLabel: Performance Score
| Department | Q1 Score | Q2 Score |
|------------|---------|----------|
| Human Resources Management | 85 | 88 |
| Information Technology Services | 92 | 94 |
| Customer Success and Support | 78 | 82 |
| Sales and Business Development | 90 | 93 |
| Marketing and Communications | 87 | 89 |
| Product Development and Engineering | 95 | 97 |
| Operations and Logistics | 83 | 85 |
| Finance and Accounting | 88 | 91 |
| Legal and Compliance | 82 | 84 |
| Research and Development | 91 | 93 |
\`\`\`

### Expected Behavior

Charts with many data points should:
- ✅ Rotate x-axis labels at -45° when there are more than 6 data points
- ✅ Truncate long labels with "..." when there are more than 4 data points AND average label length > 15 chars
- ✅ Truncate at word boundaries when possible for better readability
- ✅ Show fewer labels (interval) when there are many data points (12+)
- ✅ Increase bottom margin to accommodate rotated labels
- ✅ Prevent overlap between rotated labels and x-axis title (extra margin when both present)
- ✅ Prevent overlap between rotated labels and legend (extra margin when both present)
- ✅ Keep labels horizontal when there are 6 or fewer data points
- ✅ All labels should be readable without overlapping
- ✅ Tooltips should show FULL original labels even when axis labels are truncated
- ✅ Short labels should NOT be truncated unnecessarily (smart truncation)`
  },
  {
    title: 'Bug Reproduction',
    content: `## Bug Reproduction

Test cases for reported math rendering issues.

1. Integral with thin space: $\\int 2x\\,dx$
2. Integral equation: $\\int 2x\\,dx = x^2 + C$
3. Function integral: $\\int f(x)\\,dx = F(x) + C$

Raw source check (escaped for JS string):
\`$\\int 2x\\,dx$\`
`
  }
];

// Streaming chart test data - simulates partial data arriving from LLM
export const streamingChartStages = {
  title: 'Chart Streaming Simulation',
  stages: [
    // Stage 1: Just the type and title
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month |`,
    // Stage 2: Partial header
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month | Total Orders | Total Revenue |`,
    // Stage 3: Complete header with separator
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|`,
    // Stage 4: First two rows
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|
| January | 156 | 15234.50 | 548.23 | 142 |
| February | 143 | 14567.80 | 512.67 | 128 |`,
    // Stage 5: Partial third row (incomplete)
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|
| January | 156 | 15234.50 | 548.23 | 142 |
| February | 143 | 14567.80 | 512.67 | 128 |
| March | 168 | 16789.25 |`,
    // Stage 6: More rows
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|
| January | 156 | 15234.50 | 548.23 | 142 |
| February | 143 | 14567.80 | 512.67 | 128 |
| March | 168 | 16789.25 | 578.45 | 155 |
| April | 125 | 14052.14 | 562.09 | 118 |`,
    // Stage 7: Complete data
    `\`\`\`chart
type: line
title: Monthly E-commerce Metrics
showLegend: true
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|
| January | 156 | 15234.50 | 548.23 | 142 |
| February | 143 | 14567.80 | 512.67 | 128 |
| March | 168 | 16789.25 | 578.45 | 155 |
| April | 125 | 14052.14 | 562.09 | 118 |
| May | 189 | 18234.67 | 601.23 | 172 |
| June | 201 | 19567.89 | 623.45 | 185 |
| July | 178 | 17234.56 | 589.12 | 163 |
| August | 145 | 14789.34 | 545.67 | 132 |
| September | 167 | 16123.45 | 567.89 | 154 |
| October | 198 | 19012.34 | 612.34 | 181 |
| November | 223 | 22345.67 | 645.78 | 205 |
| December | 256 | 25678.90 | 678.90 | 234 |
\`\`\``,
  ],
  // Full final content for comparison
  finalContent: `## Chart Streaming Test - Complete

This test demonstrates how charts handle streaming data from an LLM. The chart should:
- Show a loading indicator while data is incomplete
- Debounce rapid updates to prevent flickering
- Render smoothly once all data arrives

### Monthly E-commerce Metrics

\`\`\`chart
type: line
title: Monthly E-commerce Metrics
description: Tracking key e-commerce KPIs across the year
showLegend: true
xAxisLabel: Month
yAxisLabel: Value
| Month | Total Orders | Total Revenue | Average Order Value | Unique Customers |
|-------|--------------|---------------|---------------------|------------------|
| January | 156 | 15234.50 | 548.23 | 142 |
| February | 143 | 14567.80 | 512.67 | 128 |
| March | 168 | 16789.25 | 578.45 | 155 |
| April | 125 | 14052.14 | 562.09 | 118 |
| May | 189 | 18234.67 | 601.23 | 172 |
| June | 201 | 19567.89 | 623.45 | 185 |
| July | 178 | 17234.56 | 589.12 | 163 |
| August | 145 | 14789.34 | 545.67 | 132 |
| September | 167 | 16123.45 | 567.89 | 154 |
| October | 198 | 19012.34 | 612.34 | 181 |
| November | 223 | 22345.67 | 645.78 | 205 |
| December | 256 | 25678.90 | 678.90 | 234 |
\`\`\`

### Bar Chart with Multiple Series

\`\`\`chart
type: bar
title: Quarterly Revenue by Region
description: Regional performance comparison
showLegend: true
stacked: false
| Quarter | North America | Europe | Asia Pacific | Latin America |
|---------|---------------|--------|--------------|---------------|
| Q1 | 125000 | 95000 | 78000 | 45000 |
| Q2 | 145000 | 110000 | 92000 | 52000 |
| Q3 | 132000 | 102000 | 85000 | 48000 |
| Q4 | 168000 | 125000 | 105000 | 62000 |
\`\`\`

### Pie Chart Distribution

\`\`\`chart
type: pie
title: Market Share by Product Category
data: [35, 28, 22, 15]
labels: [Electronics, Clothing, Home & Garden, Sports]
colors: [#3b82f6, #8b5cf6, #ec4899, #10b981]
\`\`\`
`,
};

// Test case for multiple charts updating simultaneously
export const multiChartStreamingContent = `## Multiple Charts - Streaming Stress Test

This tests multiple charts rendering simultaneously, which is common when an LLM returns a comprehensive analysis.

### Revenue Trend

\`\`\`chart
type: area
title: Monthly Revenue Trend
showLegend: true
| Month | Revenue | Projected |
|-------|---------|-----------|
| Jan | 45000 | 42000 |
| Feb | 52000 | 48000 |
| Mar | 48000 | 50000 |
| Apr | 61000 | 55000 |
| May | 55000 | 58000 |
| Jun | 67000 | 62000 |
\`\`\`

### Customer Segmentation

\`\`\`chart
type: pie
title: Customer Segments
data: [40, 30, 20, 10]
labels: [Enterprise, SMB, Consumer, Government]
\`\`\`

### Product Performance

\`\`\`chart
type: bar
title: Product Category Performance
stacked: true
| Category | Online | Retail | Wholesale |
|----------|--------|--------|-----------|
| Electronics | 85000 | 65000 | 45000 |
| Clothing | 62000 | 78000 | 32000 |
| Food | 45000 | 92000 | 68000 |
| Home | 38000 | 55000 | 28000 |
\`\`\`

### Composed Analysis

\`\`\`chart
type: composed
title: Sales vs Conversion Rate
showLegend: true
series: [
  {"key":"Sales","type":"bar","name":"Sales ($)","color":"#3b82f6"},
  {"key":"Conversion","type":"line","name":"Conversion (%)","color":"#ef4444","yAxisId":"right","strokeWidth":3}
]
yAxisLabel: Sales ($)
yAxisRightLabel: Conversion (%)
| Month | Sales | Conversion |
|-------|-------|------------|
| Jan | 12000 | 2.5 |
| Feb | 15000 | 3.1 |
| Mar | 18000 | 3.8 |
| Apr | 14000 | 2.9 |
| May | 21000 | 4.2 |
| Jun | 25000 | 4.8 |
\`\`\`
`;

export const stressTestContent = `# Stress Test Content

${Array(50).fill(null).map((_, i) => `## Heading ${i + 1}

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

`).join('\n')}

### Massive Table

| ${'Column | '.repeat(10)}
| ${'--- | '.repeat(10)}
${Array(50).fill(null).map((_, i) => `| ${'Cell ' + i + ' | '.repeat(10)}`).join('\n')}

### Many Math Expressions

${Array(20).fill(null).map((_, i) => `The formula $x_${i} = \\frac{${i}}{${i + 1}}$ represents the relationship between variables.`).join(' ')}

### Code Block Spam

${Array(10).fill(null).map((_, i) => `\`\`\`javascript
function test${i}() {
  console.log("Test ${i}");
  return ${i} * 2;
}
\`\`\`

`).join('\n')}
`;

export default testCases;
