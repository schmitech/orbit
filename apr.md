# Changelog

**Period:** 2026-04-07 to 2026-04-19
**Generated:** 2026-04-19 10:41:11

## Summary

- **Total commits:** 28
- **Features:**        0
- **Bug fixes:**        0
- **Other changes:**       28

## 🚀 Features

_No new features in this period._

## 🐛 Bug Fixes

_No bug fixes in this period._

## 📝 Other Changes

- Fix #127: Apply adapter toggle immediately in runtime (schmitech, 2026-04-19)
- Sanitize provider errors before returning to client (schmitech, 2026-04-19)
- Add audit in admin panel (schmitech, 2026-04-18)
- Add admin events auditing (schmitech, 2026-04-18)
- Improve README (schmitech, 2026-04-18)
- Create mongo sqlite sync util (schmitech, 2026-04-17)
- OpenAI unit test (schmitech, 2026-04-17)
- Set openai as default model (schmitech, 2026-04-16)
- Modernize file upload UI (schmitech, 2026-04-16)
- Remove policestats project (schmitech, 2026-04-15)
- Add composite cross-adapter template hot reload (schmitech, 2026-04-15)
- Increase max length persona (schmitech, 2026-04-14)
- Put back policestats example (schmitech, 2026-04-14)
- Updates: orbitchat and admin panel (schmitech, 2026-04-14)
- Minor refatoring (schmitech, 2026-04-14)
- Redesign autocomplete (schmitech, 2026-04-13)
- Bulk delete (schmitech, 2026-04-13)
- Add sitemap, robots.txt, and agent SEO content for orbitchat (schmitech, 2026-04-13)
- Remove sandbox examples (schmitech, 2026-04-13)
- admin-panel: User management updates (schmitech, 2026-04-12)
- Refine admin panel workflows (schmitech, 2026-04-10)
- Enable pagination for long lists (schmitech, 2026-04-10)
- Minor UI updates (schmitech, 2026-04-10)
- Harden autocomplete service, added new agent (schmitech, 2026-04-09)
- Added cross-adapter templates (schmitech, 2026-04-09)
- Fix realtime voice prompt and adapter resolution (schmitech, 2026-04-08)
- feat(voice): OpenAI Realtime WebSocket adapter (schmitech, 2026-04-08)
- Enabled composite adapter (schmitech, 2026-04-07)
---

## 📋 Complete Commit History

_All commits in chronological order with full details for AI summarization:_

### Enabled composite adapter
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-07 13:57:39
**Hash:** bef691e3

**Description:**
Enabled composite adapter

Updated composite adapter and add demo link in README file. Reorganize prompt examples.

---
### feat(voice): OpenAI Realtime WebSocket adapter
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-08 10:30:49
**Hash:** 426aa333

**Description:**
feat(voice): OpenAI Realtime WebSocket adapter

Add open-ai-real-time-voice-chat (type: openai_realtime) bridging ORBIT’s /ws/voice JSON protocol to OpenAI’s Realtime WebSocke. Register openai_realtime in the adapter registry so loading no longer fails. Introduce clients/openai-realtime-voice (Vite) for manual testing.

---
### Fix realtime voice prompt and adapter resolution
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-08 12:55:29
**Hash:** e06ea630

**Description:**
Fix realtime voice prompt and adapter resolution

Route voice websocket adapter selection through API key resolution, load OpenAI Realtime session instructions from prompt service instead of static config, tighten VAD defaults to reduce false turns, and add logging/debug coverage for prompt loading and voice turn events.

---
### Added cross-adapter templates
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-09 11:37:33
**Hash:** 37ae8d33

**Description:**
Added cross-adapter templates

Support for cross-domain intent templates on top of individual adapters.

---
### Harden autocomplete service, added new agent
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-09 15:48:29
**Hash:** d6cf302c

**Description:**
Harden autocomplete service, added new agent

Improves autocomplete robustness on both server and client. The service now sanitizes and deduplicates nl_examples, clamps limits to config, uses single-flight cache population, and prefilters fuzzy candidates by relevance instead of naive truncation. The client keeps better fallback behavior, avoids permanently disabling adapters on transient failures, and again sends the proxy-required X-Adapter-Name and session headers for /api/v1/ autocomplete. Added another agent based on nasa's best coding principles. Detach business analytivd adapter into its own file.

---
### Minor UI updates
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-10 09:11:08
**Hash:** 02986598

**Description:**
Minor UI updates

Added clipboard icon for api key field. Updated api key / password mask toggle icon.

---
### Enable pagination for long lists
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-10 10:00:18
**Hash:** ddc4ebd9

**Description:**
Enable pagination for long lists

Redesign list component and use pagination to avoid long vertical scrolling.

---
### Refine admin panel workflows
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-10 11:38:14
**Hash:** fd92ac43

**Description:**
Refine admin panel workflows

Improve the admin panel UX across API keys, personas, adapters, and overview monitoring. Add dedicated adapter management, remove adapter controls from Ops, and convert overview health sections to compact searchable/paginated tables with cleaner summary cards. Rework API key and persona tabs so create forms are hidden behind list-level + Create actions, detail views stay read-only until explicit edit, persona edits update immediately without full reload, persona renames propagate to associated API key metadata, markdown notes render in API key details, and several spacing/title/dropdown issues are cleaned up.

---
### admin-panel: User management updates
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-12 08:57:58
**Hash:** 4ceaebbc

**Description:**
admin-panel: User management updates

Improve user management in admin panel.

---
### Remove sandbox examples
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-13 10:43:08
**Hash:** a0c3db13

**Description:**
Remove sandbox examples

No more sandbox examples.

---
### Add sitemap, robots.txt, and agent SEO content for orbitchat
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-13 14:31:17
**Hash:** f0fd3770

**Description:**
Add sitemap, robots.txt, and agent SEO content for orbitchat

Introduce YAML-driven SEO settings for orbitchat, generate sitemap.xml and robots.txt from config, add per-agent metadata/canonical handling, and render backend agent notes on agent landing pages for indexing.

---
### Bulk delete
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-13 18:49:04
**Hash:** eb395d70

**Description:**
Bulk delete

Ability to perform bulk deletion on lists (users, api keys, personas).

---
### Redesign autocomplete
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-13 19:15:03
**Hash:** 7db94df5

**Description:**
Redesign autocomplete

Move autocomplete suggestions from a floating card above the input to clean full-width rows below it. Typed portion shows in muted gray, completion in bold. Remove keyboard hint bar. Mobile-friendly touch targets preserved.

---
### Minor refatoring
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-14 11:03:51
**Hash:** 941b4e8f

**Description:**
Minor refatoring

Move nh3 and markdown to default profile.

---
### Updates: orbitchat and admin panel
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-14 16:00:32
**Hash:** 63d28faa

**Description:**
Updates: orbitchat and admin panel

Switch mobile input to single-row layout with only essential buttons (attach + send) visible. Hide voice toggle, mic, and help buttons on mobile. Shorten "Continue Discussion" to "Continue", keep all action buttons on one row, reposition feedback toast above thumbs, fix placeholder text overflow with truncation, and remove persistent hover background on selected feedback thumbs. Tighten admin-panel input validation behavior and UX across users, API keys, and personas. Clear stale validation errors when fields are corrected, align reset-password guidance with shared password rules, add bulk deletion for list tabs, refresh API key adapter options after adapter creation, and add live character counters while increasing notes/persona text limits to 2000 characters with
  matching backend schema validation.

---
### Put back policestats example
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-14 17:02:15
**Hash:** 18d70521

**Description:**
Put back policestats example

Bring back built with orbit section.

---
### Increase max length persona
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-14 20:32:41
**Hash:** f3f63e2d

**Description:**
Increase max length persona

Increased max length for persona text field from 2000 to 10000 characters.

---
### Add composite cross-adapter template hot reload
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-15 11:32:37
**Hash:** 5d92c804

**Description:**
Add composite cross-adapter template hot reload

Implement template reload for CompositeIntentRetriever so the existing admin reload flow also rebuilds cross-adapter template embeddings and vector collections. Add tests covering composite cross-adapter reload and the disabled/no-op path.

---
### Remove policestats project
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-15 16:55:22
**Hash:** 092b173c

**Description:**
Remove policestats project

Remove project reference.

---
### Modernize file upload UI
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-16 15:54:16
**Hash:** 20034dec

**Description:**
Modernize file upload UI

- Redesign file upload drop zone: replace dashed border with clean horizontal layout, icon badge, and subtle hover transitions
- Modernize progress rows with animated background fill, slim progress bar, and percentage readout
- Redesign success/error/warning banners: remove borders, add semantic icons, use app color tokens
- Add 120s processing timeout in backend to prevent files stuck in 'processing' forever
- Propagate error_message from backend through frontend (FileAttachment type, getFileInfo, listFiles, pollFileStatus)
- Show failed files with red error state in file pills instead of infinite spinner
- Clean up progress entries when files transition to failed/completed status
- Skip confirmation dialog when dismissing failed file pills

---
### Set openai as default model
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-16 15:58:55
**Hash:** 8466b51e

**Description:**
Set openai as default model

Use openai gpt-5.4-mini as default.

---
### OpenAI unit test
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-17 07:29:53
**Hash:** c38a8ca0

**Description:**
OpenAI unit test

Added openai test.

---
### Create mongo sqlite sync util
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-17 13:24:52
**Hash:** af99c954

**Description:**
Create mongo sqlite sync util

New script to sync up api keys and personas from/to mongo and sqlite backend.

---
### Improve README
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-18 11:07:20
**Hash:** d7b9b502

**Description:**
Improve README

Update README content.

---
### Add admin events auditing
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-18 19:37:21
**Hash:** f1b939bd

**Description:**
Add admin events auditing

New audit module for admin events.

---
### Add audit in admin panel
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-18 20:09:03
**Hash:** 6b0cfcda

**Description:**
Add audit in admin panel

Add new audit view.

---
### Sanitize provider errors before returning to client
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-19 09:17:03
**Hash:** 68f46a6f

**Description:**
Sanitize provider errors before returning to client

Raw provider SDK exceptions (e.g. OpenAI "Error code: 401 - Your IP is not authorized...") were being streamed back to clients as response chunks, leaking account-, network-, and policy-level detail.

---
### Fix #127: Apply adapter toggle immediately in runtime
**Author:** schmitech (remsy.schmilinsky@schmitech.ca)
**Date:** 2026-04-19 10:33:23
**Hash:** 133763bc

**Description:**
Fix #127: Apply adapter toggle immediately in runtime

The admin toggle endpoint (PATCH /admin/adapters/config/entry/{name}/toggle) wrote enabled: true/false to the YAML but never notified DynamicAdapterManager, so disabled adapters remained usable from the client until a manual "Reload Adapter" click. The handler now calls reload_adapters_config(config_path) and adapter_manager.reload_adapters(new_config, adapter_name) after the write, reusing the existing single-adapter reload path which evicts the cached instance and removes the entry from AdapterConfigManager on disable (or preloads on  enable). Response includes reload_summary / reload_error so UI can surface runtime-sync failures instead of claiming silent success.

---

---

_This changelog was automatically generated from git commit history._
