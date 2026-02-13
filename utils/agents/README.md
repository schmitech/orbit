# Code Quality & Security Assessment Agents

A pair of reusable prompt frameworks for conducting thorough code reviews and security vulnerability assessments using AI assistants (Claude, Codex, or similar).

---

## What's Included

| File | Purpose |
|------|---------|
| `code-review-agent.md` | Evaluates code quality, design principles (SOLID, DRY, KISS), clean code practices, performance, and maintainability |
| `security-audit-agent.md` | Identifies security vulnerabilities, assesses severity, and provides concrete mitigations |

---

## Quick Start

### 1. Pick the right agent

- **Code needs optimization, refactoring, or cleanup?** → Use `code-review-agent.md`
- **Need to find security risks and vulnerabilities?** → Use `security-audit-agent.md`
- **Want both?** → Combine them in a single session (see below)

### 2. Start a new conversation with your AI assistant

Paste or attach the agent prompt, preceded by this instruction:

```
Apply the following assessment framework to the attached codebase:
```

Then attach or paste your code below it.

### 3. Read the output

Both agents produce structured findings with locations, explanations, and fixes, followed by a summary with prioritized recommendations.

---

## Usage Examples

### Single Agent — Code Review

```
Apply the following assessment framework to the attached codebase:

[Paste contents of code-review-agent.md here]

[Paste or attach your code]
```

### Single Agent — Security Audit

```
Apply the following assessment framework to the attached codebase:

[Paste contents of security-audit-agent.md here]

[Paste or attach your code]
```

### Combined — Full Review

```
Using the following assessment frameworks, conduct a comprehensive code quality
review and security vulnerability assessment of the attached codebase. Address
all findings in the specified output formats:

[Paste contents of code-review-agent.md here]

[Paste contents of security-audit-agent.md here]

[Paste or attach your code]
```

---

## Optional Modifiers

Append any of these lines after the agent prompt to steer the review toward your specific needs.

### Context Modifiers

```
This is a [Python/TypeScript/Java/Go/Rust] application using [framework].
The database is [Postgres/MongoDB/Redis/etc.].
This is deployed on [AWS/GCP/Azure/self-hosted].
```

### Focus Modifiers

```
Focus especially on [performance / readability / testability / security].
Focus especially on [API security / auth flows / data protection / third-party integrations].
```

### Scope Modifiers

```
Only refactor — don't change external APIs or behavior.
This is exposed to the public internet / internal only.
This handles [payment data / health records / PII].
```

### Compliance Modifiers

```
Also check for [OWASP Top 10 / SOC 2 / HIPAA / PCI-DSS] compliance where relevant.
```

---

## Tips for Best Results

1. **Provide full files, not snippets.** The more context the agent has, the better the analysis. Partial code leads to missed issues and false positives.

2. **Specify your stack.** Adding your language, framework, and database helps the agent give relevant, idiomatic recommendations instead of generic advice.

3. **Run both agents.** Code quality and security are complementary. A well-structured codebase is easier to secure, and a security review often catches logic issues a code review misses.

4. **Iterate.** After applying the suggested fixes, run the agent again on the updated code. Some improvements reveal deeper issues that weren't visible before.

5. **Use focus modifiers for large codebases.** If you're reviewing a large project, break it into modules and use focus modifiers to prioritize what matters most for each section.

6. **Review the fixes before applying.** These agents provide high-quality suggestions, but always validate that the refactored code preserves your intended behavior and passes your existing tests.

---

## Output You Can Expect

### Code Review Agent

For each issue:
- **Location** — file and line/section
- **Issue** — what's wrong and which principle it violates
- **Why it matters** — concrete risk (bugs, tech debt, performance, readability)
- **Fix** — refactored code

Summary includes:
- Top 3 highest-impact improvements
- Overall code health score (1–10)
- Architectural recommendations

### Security Audit Agent

For each vulnerability:
- **Location** — file and line/section
- **Vulnerability** — name and type (e.g., Reflected XSS, Hardcoded API Key)
- **Severity** — Critical / High / Medium / Low
- **Attack Scenario** — how it could be exploited
- **Mitigation** — specific fix with refactored code

Summary includes:
- Findings count by severity
- Top 3 most urgent fixes
- Overall security posture score (1–10)
- Tooling and process recommendations

---

## Compatibility

These prompts are designed to work with any capable AI coding assistant, including:

- **Claude** (Anthropic) — claude.ai or API
- **Claude Code** — CLI tool
- **OpenAI Codex / ChatGPT** — chat or API
- **Cursor, Windsurf, Copilot Chat** — IDE-integrated assistants

---

## License

Free to use, modify, and distribute. No attribution required.