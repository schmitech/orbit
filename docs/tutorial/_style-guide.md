# Tutorial Style Guide

Internal convention for everyone writing or editing ORBIT tutorial pages under `docs/tutorial/`. Not itself a tutorial — skip this if you're just here to learn ORBIT.

## Learning levels

ORBIT's tutorials are organized into a leveled learning path (see [tutorial.md](../tutorial.md)):

| Level | Name | Audience |
|---|---|---|
| **L0** | Orientation | Zero ORBIT experience — install, first chat, admin panel tour |
| **L1** | Foundations | New to ORBIT's adapter model — simplest adapters, one concept at a time |
| **L2** | Core AI Services | Understands one adapter, ready to learn what's underneath (inference/datasources/embeddings) |
| **L3** | Intermediate adapters & composition | Ready to combine sources — intent adapters, composite, HTTP |
| **L4** | Skills, MCP tools & generation | Ready for "the model does things," not just answers |
| **L5** | Advanced / production | Comfortable with the basics, deploying for real |

Every tutorial page opens with a level badge directly under its H1, e.g.:

```markdown
# Connecting Your Own Data

**Level 1 · Foundations**

...
```

Reference-only pages (level-agnostic, read as needed rather than in sequence) use:

```markdown
**Reference · read as needed**
```

## Media placeholders

Screenshots and videos are not yet available for most pages. Mark every spot where one belongs with an HTML comment (grep-able) immediately followed by a visible callout, so the page still reads coherently on GitHub before the asset exists:

```markdown
<!-- MEDIA: screenshot | admin-panel/adapters-tab | Adapters tab showing an active QA adapter -->
> 🖼️ **Screenshot placeholder:** Adapters tab showing an active QA adapter.
> _(To be added — see docs/tutorial/_media-todo.md)_
```

```markdown
<!-- MEDIA: video | first-chat-walkthrough | 90s walkthrough: create persona -> create API key -> send first chat -->
> 🎬 **Video placeholder:** 90-second walkthrough of creating a persona, API key, and first chat.
```

Rules:
- The `MEDIA:` prefix is the only string that needs to be grepped later (`grep -rn "<!-- MEDIA:" docs/tutorial/`) — trivial to find-and-replace with real `![alt](path)` syntax or an embed once assets exist.
- Second field is `screenshot` or `video`.
- Third field is a stable slug matching the future asset path convention: `docs/assets/tutorial/<slug>.png` or `.mp4`.
- Fourth field is a plain-language brief for whoever captures the screenshot or records the video — describe exactly what should be visible.
- Every placeholder you add must also get a row in [`_media-todo.md`](_media-todo.md) — that file is the single checklist for filling in real assets later, so it must stay in sync with what's actually in the docs.

## Cross-linking

- Link forward to the next level at the end of a page's content ("Next: ...").
- Link out to deep-reference docs (`docs/adapters/*.md`) rather than duplicating their content — the tutorial layer teaches the concept at onboarding depth; the adapters/reference layer is where the full depth lives.
- Never link to `docs/adapters/playbook-*.md` files from tutorial pages — those are internal manual-QA checklists, not learner content.
